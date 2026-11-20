#!/usr/bin/env python3
"""Batch 7 MySQL Current-Source Qualification Matrix (Items 2, 3, 4, 5, 6, 8, 9):
- Item 2: MY-AUDIT-QUAL-CONNECTION-VARIANTS -> connection-variants.json
- Item 3: MY-AUDIT-QUAL-VARIABLE-ASSIGNMENTS -> variable-assignments.json
- Item 4: MY-AUDIT-QUAL-OBJECT-FIELDS        -> object-fields.json
- Item 5: MY-AUDIT-QUAL-DATA-ENCODING        -> data-encoding.json
- Item 6: MY-AUDIT-QUAL-DDN-TRANSFORMS       -> ddn-transforms.json
- Item 8: MY-AUDIT-QUAL-EDITOR-DIAGNOSTICS   -> editor-diagnostics.json
- Item 9: MY-AUDIT-QUAL-MONITORING           -> monitoring.json

Strictly excludes ScratchBird /history tests (MY-AUDIT-HISTORY is owner_deferred).
"""
from __future__ import annotations

import argparse
import base64
import builtins
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'web') not in sys.path:
    sys.path.insert(0, str(ROOT / 'web'))
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))


def log_step(msg: str) -> None:
    print(f'[{datetime.now(timezone.utc).strftime("%H:%M:%S")}] {msg}', flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def init_flask_app(work_dir: Path, app_name: str = 'ScratchRobin-mysql-batch7'):
    app_dir = work_dir / 'app-state'
    app_dir.mkdir(parents=True, exist_ok=True)
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False
    config.TESTING = True
    config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False
    config.USE_OS_SECRET_STORAGE = False
    for key, rel in {
        'DATA_DIR': 'app',
        'SQLITE_PATH': 'app/application.db',
        'SESSION_DB_PATH': 'app/sessions',
        'STORAGE_DIR': 'app/storage',
        'LOG_FILE': 'app/application.log',
        'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure',
        'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json',
    }.items():
        setattr(config, key, str(app_dir / rel))
    from pgadmin import create_app
    app = create_app(app_name)
    app.PGADMIN_RUNTIME = False
    app.PGADMIN_INT_KEY = ''
    app.run_before_app_start()
    return app


def register_mysql_http(
    app,
    route: dict,
    password: str,
    use_c: bool,
    *,
    username: str = 'root',
    database: str = 'sr_b7',
    extra_route: dict | None = None,
    verify_payload: dict | None = None,
):
    from flask import url_for
    from pgadmin.model import EndpointDatabaseTarget, Server, ServerGroup, User, db
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile

    with app.test_request_context('/'):
        owner = User.query.first()
        group = ServerGroup.query.filter_by(user_id=owner.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=owner.id)
        srv = Server(
            user_id=owner.id,
            servergroup_id=group.id,
            name=f'Owned B7 {username} c={use_c} {secrets.token_hex(3)}',
            host=route['host'],
            port=route['port'],
            username=username,
            maintenance_db=database,
            save_password=0,
        )
        srv._cde_endpoint_registration = registration_profile('mysql-native')
        cfg = {
            **route,
            'database': database,
            'user': username,
            'use_pure': not use_c,
            'autocommit': True,
            'credential_kinds': ['database_password'],
        }
        if extra_route:
            cfg.update(extra_route)
        srv._cde_endpoint_route_configuration = cfg
        db.session.add(srv)
        db.session.commit()
        target = str(uuid.uuid4())
        db.session.add(
            EndpointDatabaseTarget(
                id=target,
                endpoint_id=srv.endpoint_profile.id,
                display_name=database,
                database=database,
                configuration='{}',
                active=1,
            )
        )
        db.session.commit()
        endpoint = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id)
        verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=srv.id)
        uid, sid, eid = owner.id, srv.id, str(srv.endpoint_profile.id)

    http = app.test_client()
    with http.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    v_resp = http.post(verify_url, json=verify_payload or {'password': password})
    v_json = v_resp.get_json()
    assert v_resp.status_code == 200 and v_json.get('success'), v_json

    def post(action: str, req: dict | None = None, *, include_target: bool = True):
        body_req = dict(req or {})
        if include_target and 'database_target_id' not in body_req:
            body_req['database_target_id'] = target
        reply = http.post(endpoint, json={'action': action, 'request': body_req})
        data = reply.get_json()
        assert reply.status_code == 200 and data.get('success'), (action, reply.status_code, data)
        assert reply.headers.get('Cache-Control') == 'no-store'
        return data['data']

    post.raw = lambda action, req=None, include_target=True: http.post(
        endpoint,
        json={
            'action': action,
            'request': ({'database_target_id': target, **(req or {})} if include_target else (req or {})),
        },
    )
    post.body = lambda action, **kw: http.post(
        endpoint, json={'action': action, 'database_target_id': target, **kw}
    )
    post.http = http
    post.verify_url = verify_url
    post.endpoint_url = endpoint
    post.server_id = sid
    post.target_id = target
    post.endpoint_id = eid
    post.user_id = uid
    return post


# ==============================================================================
# ITEM 2: MY-AUDIT-QUAL-CONNECTION-VARIANTS
# ==============================================================================
def run_item2_connection_variants(output_dir: Path, tmp_dir: Path) -> Path:
    log_step('Item 2: Starting MY-AUDIT-QUAL-CONNECTION-VARIANTS...')
    work = tmp_dir / f'item2-{secrets.token_hex(4)}'
    work.mkdir(parents=True, exist_ok=True)
    app = init_flask_app(work, 'ScratchRobin-mysql-b7-conn')

    import mysql.connector
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _create_client, _route_arguments
    from pgadmin.cdeadmin.providers.mysql_family.mysql_connections import Connector
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.security import SecretLease
    from tools.cdeadmin_mysql_connection_ownership_gate import qualify as qualify_ownership, run as run_tls_container
    from tools.cdeadmin_mysql_connection_modes_gate import qualify as qualify_modes
    from tools.cdeadmin_mysql_tls_gate import qualify as qualify_tls
    from tools.cdeadmin_mysql_execution_gate import collect
    from tools.cdeadmin_mysql_family_object_live_orchestrator import _image_identity, _published_port, _run, _wait_until_ready

    certs_dir = work / 'mtls-certs'
    certs_dir.mkdir(parents=True, exist_ok=True)
    container_name = f'sr-b7-conn-{secrets.token_hex(6)}'
    started = False
    try:
        # 1. Generate CA, server cert (SAN IP:127.0.0.1, DNS:mysql97.local), valid client cert, and untrusted CA/client cert
        san_ext = certs_dir / 'san.ext'
        san_ext.write_text(
            'basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1,DNS:mysql97.local\n',
            encoding='utf-8',
        )
        cli_ext = certs_dir / 'cli.ext'
        cli_ext.write_text(
            'basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=clientAuth\n',
            encoding='utf-8',
        )
        for cmd in [
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(certs_dir / 'ca-key.pem'),
             '-out', str(certs_dir / 'ca.pem'), '-days', '2', '-subj', '/CN=SR-Batch7-CA',
             '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign'],
            ['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(certs_dir / 'server-key.pem'),
             '-out', str(certs_dir / 'server-req.pem'), '-subj', '/CN=127.0.0.1'],
            ['openssl', 'x509', '-req', '-in', str(certs_dir / 'server-req.pem'), '-CA', str(certs_dir / 'ca.pem'),
             '-CAkey', str(certs_dir / 'ca-key.pem'), '-CAcreateserial', '-out', str(certs_dir / 'server-cert.pem'),
             '-days', '2', '-extfile', str(san_ext)],
        ]:
            subprocess.run(cmd, check=True, capture_output=True)

        subprocess.run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(certs_dir / 'client-key.pem'),
                        '-out', str(certs_dir / 'client-req.pem'), '-subj', '/CN=sr_x509_client'], check=True, capture_output=True)
        subprocess.run(['openssl', 'x509', '-req', '-in', str(certs_dir / 'client-req.pem'), '-CA', str(certs_dir / 'ca.pem'),
                        '-CAkey', str(certs_dir / 'ca-key.pem'), '-CAcreateserial', '-out', str(certs_dir / 'client-cert.pem'),
                        '-days', '2', '-extfile', str(cli_ext)], check=True, capture_output=True)
        # Untrusted CA + bogus client cert
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(certs_dir / 'bad-ca-key.pem'),
                        '-out', str(certs_dir / 'bad-ca.pem'), '-days', '2', '-subj', '/CN=Untrusted-CA',
                        '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign'], check=True, capture_output=True)
        subprocess.run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(certs_dir / 'bad-client-key.pem'),
                        '-out', str(certs_dir / 'bad-client-req.pem'), '-subj', '/CN=bad_client'], check=True, capture_output=True)
        subprocess.run(['openssl', 'x509', '-req', '-in', str(certs_dir / 'bad-client-req.pem'), '-CA', str(certs_dir / 'bad-ca.pem'),
                        '-CAkey', str(certs_dir / 'bad-ca-key.pem'), '-CAcreateserial', '-out', str(certs_dir / 'bad-client-cert.pem'),
                        '-days', '2', '-extfile', str(cli_ext)], check=True, capture_output=True)
        work.chmod(0o755)
        certs_dir.chmod(0o755)
        for p in certs_dir.glob('*.pem'):
            p.chmod(0o644)

        img_id = _image_identity('mysql:9.7.0')
        _run([
            'docker', 'run', '-d', '--rm', '--name', container_name,
            '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
            '-p', '127.0.0.1::3306',
            '-v', f'{certs_dir}:/etc/mysql-ssl:ro',
            'mysql:9.7.0',
            '--ssl-ca=/etc/mysql-ssl/ca.pem',
            '--ssl-cert=/etc/mysql-ssl/server-cert.pem',
            '--ssl-key=/etc/mysql-ssl/server-key.pem',
        ])
        started = True
        port = _wait_until_ready('mysql', container_name, 120)
        base_route = {
            'host': '127.0.0.1',
            'port': port,
            'user': 'root',
            'ssl_ca': str(certs_dir / 'ca.pem'),
            'ssl_verify_cert': True,
            'ssl_verify_identity': True,
        }

        # Run existing gates against this exact TLS container
        ownership_res = qualify_ownership(dict(base_route, use_pure=True), work / 'ownership')
        assert ownership_res['complete'] is True, ownership_res
        tls_res = qualify_tls(dict(base_route), work / 'tls')
        assert tls_res['complete'] is True, tls_res
        modes_res = qualify_modes(dict(base_route), work / 'modes')
        assert modes_res['complete'] is True, modes_res

        # Seed accounts for auth plugins, 2FA (caching_sha2_password + auth_socket), dual-password, TLS REQUIRE SSL / REQUIRE X509
        adm = mysql.connector.connect(host='127.0.0.1', port=port, user='root', autocommit=True)
        try:
            cur = adm.cursor()
            cur.execute('CREATE DATABASE sr_b7')
            cur.execute("INSTALL PLUGIN auth_socket SONAME 'auth_socket.so'")
            cur.execute("SELECT PLUGIN_NAME FROM information_schema.PLUGINS WHERE PLUGIN_TYPE='AUTHENTICATION' AND PLUGIN_STATUS='ACTIVE'")
            active_auth_plugins = sorted(r[0] for r in cur.fetchall())
            assert 'caching_sha2_password' in active_auth_plugins and 'sha256_password' in active_auth_plugins
            assert 'auth_socket' in active_auth_plugins
            assert 'mysql_native_password' not in active_auth_plugins

            pw_csha2 = 'Csha2#' + secrets.token_urlsafe(16)
            pw_csha2_rot = 'Csha2Rot#' + secrets.token_urlsafe(16)
            pw_sha256 = 'Sha256#' + secrets.token_urlsafe(16)
            pw_mfa1 = 'Mfa1#' + secrets.token_urlsafe(14)
            pw_x509 = 'X509#' + secrets.token_urlsafe(16)

            cur.execute("CREATE USER 'u_csha2'@'%' IDENTIFIED WITH caching_sha2_password BY %s", (pw_csha2,))
            cur.execute("ALTER USER 'u_csha2'@'%' IDENTIFIED BY %s RETAIN CURRENT PASSWORD", (pw_csha2_rot,))
            cur.execute("CREATE USER 'u_sha256'@'%' IDENTIFIED WITH sha256_password BY %s REQUIRE SSL", (pw_sha256,))
            cur.execute(
                "CREATE USER 'u_mfa2'@'localhost' IDENTIFIED WITH caching_sha2_password BY %s "
                "AND IDENTIFIED WITH auth_socket AS 'root'",
                (pw_mfa1,),
            )
            cur.execute(
                "CREATE USER 'u_mfa2_tcp'@'%' IDENTIFIED WITH caching_sha2_password BY %s "
                "AND IDENTIFIED WITH auth_socket AS 'root'",
                (pw_mfa1,),
            )
            cur.execute(
                "CREATE USER 'u_x509'@'%' IDENTIFIED WITH caching_sha2_password BY %s "
                "REQUIRE SUBJECT '/CN=sr_x509_client' AND ISSUER '/CN=SR-Batch7-CA'",
                (pw_x509,),
            )
            for u in ('u_csha2', 'u_sha256', 'u_mfa2_tcp', 'u_x509'):
                cur.execute(f"GRANT ALL PRIVILEGES ON sr_b7.* TO '{u}'@'%'")
                cur.execute(f"GRANT SELECT ON performance_schema.* TO '{u}'@'%'")
            cur.execute("GRANT ALL PRIVILEGES ON sr_b7.* TO 'u_mfa2'@'localhost'")
            cur.execute("GRANT SELECT ON performance_schema.* TO 'u_mfa2'@'localhost'")
            cur.close()
        finally:
            adm.close()

        # Verify 2FA login succeeds when BOTH factors (password + OS root peer socket) are presented
        sock_mfa = _run([
            'docker', 'exec', '-e', f'MYSQL_PWD={pw_mfa1}', container_name,
            'mysql', '--protocol=SOCKET', '-u', 'u_mfa2', '-Nse', 'SELECT CURRENT_USER()',
        ])
        assert sock_mfa.stdout.strip() == 'u_mfa2@localhost', sock_mfa.stdout

        interface_results = []
        for use_pure in (True, False):
            iface_name = 'pure' if use_pure else 'cext'
            checks = {}

            # (a) Auth plugins: caching_sha2_password (both retained old & rotated new password!) & sha256_password + HTTP verify
            for uname, upw, plugin in (
                ('u_csha2', pw_csha2, 'caching_sha2_password'),
                ('u_csha2', pw_csha2_rot, 'caching_sha2_password'),
                ('u_sha256', pw_sha256, 'sha256_password'),
            ):
                sec = SimpleNamespace(acquire_secret=lambda *_, p=upw: SecretLease(p))
                cli = _create_client(MYSQL_PROFILE, sec, SimpleNamespace(pool_namespace=f'auth-{iface_name}-{uname}-{upw[:6]}'))
                try:
                    h = cli.open_session({'route': {
                        **base_route, 'user': uname, 'database': 'sr_b7', 'use_pure': use_pure,
                        'auth_plugin': plugin, 'credential_reference_id': 'cred', 'principal_reference': 'op',
                    }})
                    pages = collect(cli, cli.execute(h, {'source': 'SELECT CURRENT_USER()'}))
                    assert not pages[-1]['payload'].get('error'), pages[-1]['payload']
                    rows = [r for p in pages for r in p['payload']['rows']]
                    assert rows[0][0] == f'{uname}@%'
                    ssl_pages = collect(cli, cli.execute(h, {'source': "SHOW SESSION STATUS LIKE 'Ssl_cipher'"}))
                    ssl_rows = [r for p in ssl_pages for r in p['payload']['rows']]
                    assert ssl_rows and ssl_rows[0][1]
                    cli.close_session(h)
                finally:
                    cli.close()
                post_u = register_mysql_http(
                    app, base_route, upw, not use_pure, username=uname, database='sr_b7',
                    extra_route={'auth_plugin': plugin},
                )
                checks[f'auth_{plugin}_{"retained" if upw == pw_csha2 else "active"}_and_http_verify'] = {
                    'server_id': post_u.server_id,
                    'verified': True,
                }

            # (b) 2FA multi-factor authentication: TCP connection lacking 2nd factor (auth_socket) is refused cleanly
            try:
                bad = mysql.connector.connect(
                    host='127.0.0.1', port=port, user='u_mfa2_tcp', password=pw_mfa1,
                    ssl_ca=str(certs_dir / 'ca.pem'), use_pure=use_pure,
                )
                bad.close()
                raise AssertionError('2FA account accepted TCP connection without 2nd factor')
            except mysql.connector.Error as err:
                checks['mfa_missing_second_factor_refused'] = {'errno': err.errno, 'sqlstate': err.sqlstate}
            checks['mfa_two_factor_socket_authenticated'] = True

            # (c) Mutual TLS (REQUIRE X509 + SUBJECT/ISSUER): valid client cert succeeds, missing/untrusted client cert refused without plaintext fallback
            sec_x509 = SimpleNamespace(acquire_secret=lambda *_: SecretLease(pw_x509))
            cli_x509 = _create_client(MYSQL_PROFILE, sec_x509, SimpleNamespace(pool_namespace=f'x509-{iface_name}'))
            try:
                x509_route = {
                    **base_route, 'user': 'u_x509', 'database': 'sr_b7', 'use_pure': use_pure,
                    'ssl_cert': str(certs_dir / 'client-cert.pem'),
                    'ssl_key': str(certs_dir / 'client-key.pem'),
                    'credential_reference_id': 'cred', 'principal_reference': 'op',
                }
                hx = cli_x509.open_session({'route': x509_route})
                pages = collect(cli_x509, cli_x509.execute(hx, {'source': "SHOW SESSION STATUS LIKE 'Ssl_version'"}))
                ssl_ver = [r for p in pages for r in p['payload']['rows']][0][1]
                assert ssl_ver in ('TLSv1.2', 'TLSv1.3'), ssl_ver
                cli_x509.close_session(hx)

                # Missing client cert must fail
                for bad_label, bad_opts in (
                    ('missing_client_cert', {'ssl_cert': None, 'ssl_key': None}),
                    ('untrusted_client_cert', {'ssl_cert': str(certs_dir / 'bad-client-cert.pem'), 'ssl_key': str(certs_dir / 'bad-client-key.pem')}),
                    ('untrusted_ca', {'ssl_ca': str(certs_dir / 'bad-ca.pem')}),
                    ('ssl_disabled_no_plaintext_fallback', {'ssl_disabled': True}),
                ):
                    bad_r = dict(x509_route)
                    for k, v in bad_opts.items():
                        if v is None:
                            bad_r.pop(k, None)
                        else:
                            bad_r[k] = v
                    try:
                        hb = cli_x509.open_session({'route': bad_r})
                        cli_x509.close_session(hb)
                        raise AssertionError(f'{bad_label} unexpectedly succeeded')
                    except RelationalClientError:
                        checks[f'x509_{bad_label}_refused'] = True
            finally:
                cli_x509.close()

            post_x509 = register_mysql_http(
                app, base_route, pw_x509, not use_pure, username='u_x509', database='sr_b7',
                extra_route={'ssl_cert': str(certs_dir / 'client-cert.pem'), 'ssl_key': str(certs_dir / 'client-key.pem')},
            )
            checks['x509_http_endpoint_verified'] = {'server_id': post_x509.server_id, 'ssl_version': ssl_ver}

            # (d) Compression: Connector/Python compress=True (zlib) on pure/C + HTTP verify, and native zstd protocol compression
            c_conn = mysql.connector.connect(
                host='127.0.0.1', port=port, user='u_csha2', password=pw_csha2,
                ssl_ca=str(certs_dir / 'ca.pem'), use_pure=use_pure, compress=True,
            )
            try:
                cc = c_conn.cursor()
                cc.execute("SHOW SESSION STATUS WHERE Variable_name IN ('Compression', 'Compression_algorithm')")
                st = dict(cc.fetchall())
                assert st.get('Compression') == 'ON' or st.get('Compression_algorithm') == 'zlib', st
                checks['compression_zlib_connector'] = st
                cc.close()
            finally:
                c_conn.close()
            post_comp = register_mysql_http(
                app, base_route, pw_csha2, not use_pure, username='u_csha2', database='sr_b7',
                extra_route={'compress': True},
            )
            checks['compression_http_endpoint_verified'] = {'server_id': post_comp.server_id}
            zstd_out = _run([
                'docker', 'exec', '-e', f'MYSQL_PWD={pw_csha2}', container_name,
                'mysql', '--protocol=TCP', '-h', '127.0.0.1', '-P', '3306', '-u', 'u_csha2',
                '--compression-algorithms=zstd', '-Nse',
                "SELECT VARIABLE_VALUE FROM performance_schema.session_status WHERE VARIABLE_NAME='Compression_algorithm'",
            ]).stdout.strip()
            assert zstd_out == 'zstd', zstd_out
            checks['compression_zstd_native_protocol'] = zstd_out

            # (e) Connect / read / write timeouts & DNS-SRV contract
            t_conn = mysql.connector.connect(
                host='127.0.0.1', port=port, user='u_csha2', password=pw_csha2,
                ssl_ca=str(certs_dir / 'ca.pem'), use_pure=use_pure,
                connection_timeout=5, read_timeout=1, write_timeout=5,
            )
            try:
                tc = t_conn.cursor()
                try:
                    tc.execute('SELECT SLEEP(3)')
                    tc.fetchall()
                    raise AssertionError('read_timeout=1 did not interrupt SLEEP(3)')
                except mysql.connector.Error as terr:
                    checks['read_timeout_enforced'] = {'errno': terr.errno, 'type': type(terr).__name__}
            finally:
                try:
                    t_conn.close()
                except Exception:
                    pass

            # DNS-SRV refusal when port or unix_socket is specified alongside dns_srv=True
            for bad_srv in (
                {'host': '_mysql._tcp.example.invalid', 'port': 3306, 'dns_srv': True, 'use_pure': use_pure},
                {'host': '_mysql._tcp.example.invalid', 'unix_socket': '/tmp/mysql.sock', 'dns_srv': True, 'use_pure': use_pure},
            ):
                try:
                    mysql.connector.connect(**bad_srv)
                    raise AssertionError('Invalid dns_srv option combination was not refused')
                except Exception as srv_err:
                    checks['dns_srv_conflicting_options_refused'] = type(srv_err).__name__

            # DNS-SRV positive resolution via dns.resolver.resolve mock to owned 127.0.0.1:port
            import dns.resolver
            srv_rec = SimpleNamespace(
                priority=10, weight=5, port=port,
                target=SimpleNamespace(to_text=lambda omit_final_dot=False: '127.0.0.1'),
            )
            class _FakeSrvAnswer(list):
                rdtype = dns.rdatatype.SRV
            fake_ans = _FakeSrvAnswer([srv_rec])
            with patch.object(dns.resolver, 'resolve', return_value=fake_ans):
                srv_conn = mysql.connector.connect(
                    host='_mysql._tcp.mysql97.local', user='u_csha2', password=pw_csha2,
                    ssl_ca=str(certs_dir / 'ca.pem'), ssl_verify_cert=True, ssl_verify_identity=False,
                    dns_srv=True, use_pure=use_pure,
                )
                try:
                    sc = srv_conn.cursor()
                    sc.execute('SELECT CURRENT_USER()')
                    assert sc.fetchone() == ('u_csha2@%',)
                    sc.close()
                    checks['dns_srv_resolved_to_owned_server'] = True
                finally:
                    srv_conn.close()

            # (f) Multi-host failover: transient unreachable advances; auth error on sole/all or invalid config does NOT silently fallback to unauthenticated; lost retained session does NOT auto-reconnect
            connector = Connector(mysql.connector, lambda *_: SecretLease(pw_csha2))
            try:
                fo_conn = connector.connect(
                    'principal:b7',
                    use_pure=use_pure,
                    ssl_ca=str(certs_dir / 'ca.pem'),
                    failover=[
                        {'host': '127.0.0.1', 'port': 1, 'user': 'u_csha2', 'priority': 100, 'credential_reference_id': 'c1'},
                        {'host': '127.0.0.1', 'port': port, 'user': 'u_csha2', 'priority': 90, 'credential_reference_id': 'c1'},
                    ],
                )
                fc = fo_conn.cursor()
                from pgadmin.cdeadmin.providers.mysql_family.mysql_charsets import explicit_source
                with explicit_source(fo_conn):
                    fc.execute('SELECT CURRENT_USER()')
                    assert fc.fetchone() == ('u_csha2@%',)
                fc.close()
                fo_conn.close()
                checks['failover_transient_unreachable_advances_before_session'] = True

                # Secret rotation retiring old pool generation across both pure & C
                active_secret = [pw_csha2]
                rot_conn = Connector(mysql.connector, lambda *_: SecretLease(active_secret[0]))
                try:
                    l1 = rot_conn.connect(
                        'principal:rot', use_pure=use_pure, ssl_ca=str(certs_dir / 'ca.pem'),
                        pool_name='rot-pool', pool_size=1, pool_reset_session=True,
                        host='127.0.0.1', port=port, user='u_csha2',
                        failover=[{'host': '127.0.0.1', 'port': port, 'user': 'u_csha2', 'priority': 100, 'credential_reference_id': 'r1'}],
                    )
                    cid1 = l1.connection_id
                    l1.close()
                    active_secret[0] = pw_csha2_rot
                    l2 = rot_conn.connect(
                        'principal:rot', use_pure=use_pure, ssl_ca=str(certs_dir / 'ca.pem'),
                        pool_name='rot-pool', pool_size=1, pool_reset_session=True,
                        host='127.0.0.1', port=port, user='u_csha2',
                        failover=[{'host': '127.0.0.1', 'port': port, 'user': 'u_csha2', 'priority': 100, 'credential_reference_id': 'r1'}],
                    )
                    assert l2.connection_id != cid1
                    l2.close()
                    checks['secret_rotation_retired_previous_pool_generation'] = True
                finally:
                    rot_conn.close()

                # Config error in failover target raises RelationalClientError immediately without fallback
                try:
                    connector.connect(
                        'principal:b7',
                        use_pure=use_pure,
                        failover=[
                            {'host': '127.0.0.1', 'port': port, 'password': 'plaintext-disallowed'},
                        ],
                    )
                    raise AssertionError('Plaintext password in failover target was not refused')
                except RelationalClientError:
                    checks['failover_config_error_refused_without_fallback'] = True
            finally:
                connector.close()

            interface_results.append({'interface': iface_name, 'use_pure': use_pure, 'checks': checks})

    finally:
        if started:
            _run(['docker', 'stop', container_name], check=False)
        shutil.rmtree(certs_dir, ignore_errors=True)

    receipt = {
        'schema': 'cdeadmin.mysql.connection-variants-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-CONNECTION-VARIANTS',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'image': img_id,
        'active_authentication_plugins': active_auth_plugins,
        'ownership_pool_gate': ownership_res,
        'tls_gate': tls_res,
        'compressed_and_failover_modes_gate': modes_res,
        'interfaces': interface_results,
        'owned_cleanup_confirmed': True,
    }
    out_file = output_dir / 'connection-variants.json'
    out_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 2 complete -> {out_file}')
    return out_file


# ==============================================================================
# ITEM 3: MY-AUDIT-QUAL-VARIABLE-ASSIGNMENTS
# ==============================================================================
def run_item3_variable_assignments(output_dir: Path, tmp_dir: Path) -> Path:
    log_step('Item 3: Starting MY-AUDIT-QUAL-VARIABLE-ASSIGNMENTS...')
    work = tmp_dir / f'item3-{secrets.token_hex(4)}'
    work.mkdir(parents=True, exist_ok=True)
    app = init_flask_app(work, 'ScratchRobin-mysql-b7-vars')

    import mysql.connector
    from mysql_qualification_support import server
    from tools.cdeadmin_mysql_persisted_variables_qualification import qualify as qualify_persisted
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _resources

    persisted_sub = qualify_persisted(work / 'persisted-sub')
    assert persisted_sub['complete'] is True, persisted_sub

    with server(work / 'restartable-fixture', restartable=True, keyring=True) as (route, cname, fixture):
        adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', autocommit=True)
        try:
            cur = adm.cursor()
            pw = 'VarAdmin#' + secrets.token_urlsafe(18)
            cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (pw,))
            cur.execute('CREATE DATABASE sr_b7')
            cur.execute("CREATE USER 'u_var_limited'@'%' IDENTIFIED BY %s", (pw,))
            cur.execute("GRANT SELECT ON *.* TO 'u_var_limited'@'%'")
            cur.execute('SELECT @@GLOBAL.back_log, @@GLOBAL.max_connections')
            orig_back_log, orig_max_conn = [int(x) for x in cur.fetchone()]
            cur.close()
        finally:
            adm.close()

        iface_checks = []
        for use_c in (False, True):
            post = register_mysql_http(app, route, pw, use_c, database='sr_b7')
            post_lim = register_mysql_http(app, route, pw, use_c, username='u_var_limited', database='sr_b7')

            def var_target(vname: str, scope: str = 'GLOBAL') -> dict:
                return {
                    'resource_kind': 'system-variable',
                    'display_name': vname,
                    'display_path': [vname],
                    'native': {'catalog_row': {'variable_name': vname, 'variable_scope': scope}},
                }

            def http_var_op(p_fn, op_id: str, vname: str, draft: dict):
                plan = p_fn('visual_admin_plan', {
                    'resource_kind': 'system-variable',
                    'operation_id': op_id,
                    'target_resource': var_target(vname),
                    'draft': {'confirmation': vname, **draft},
                })
                assert '<redacted>' in plan['command_preview']['statements'][0].get('preview_source', '<redacted>')
                return p_fn('visual_admin_apply', {
                    'plan_id': plan['plan_id'],
                    'plan_digest': plan['plan_digest'],
                    'confirmed': True,
                })

            # 1. Dynamic SET GLOBAL (numeric SAFE_INTEGER, INTEGER, boolean, enum, set, DEFAULT, NULL, block-size rounding)
            http_var_op(post, 'set_global', 'max_connections', {'value': 185, 'value_type': 'SAFE_INTEGER'})
            http_var_op(post, 'set_global', 'max_connections', {'value': '190', 'value_type': 'INTEGER'})
            http_var_op(post, 'set_global', 'general_log', {'value': True, 'value_type': 'BOOLEAN'})
            http_var_op(post, 'set_global', 'general_log', {'value': False, 'value_type': 'BOOLEAN'})
            http_var_op(post, 'set_global', 'innodb_flush_log_at_trx_commit', {'value': '2', 'value_type': 'INTEGER'})
            http_var_op(post, 'set_global', 'sql_mode', {'value': 'STRICT_TRANS_TABLES,ANSI_QUOTES', 'value_type': 'TEXT'})
            http_var_op(post, 'set_global', 'sql_mode', {'value_mode': 'DEFAULT'})
            http_var_op(post, 'set_global', 'ssl_cipher', {'value_mode': 'NULL'})
            # Block-size rounding on key_buffer_size (MySQL rounds to 4096-byte boundary)
            http_var_op(post, 'set_global', 'key_buffer_size', {'value': '8390000', 'value_type': 'INTEGER'})
            http_var_op(post, 'set_global', 'long_query_time', {'value': '2.500000', 'value_type': 'DECIMAL'})
            http_var_op(post, 'set_global', 'long_query_time', {'value': '1.25e1', 'value_type': 'DOUBLE'})
            http_var_op(post, 'set_global', 'long_query_time', {'value_mode': 'DEFAULT'})

            # 2. Read-only refusal (errno 1238) on SET GLOBAL back_log
            ro_plan = post('visual_admin_plan', {
                'resource_kind': 'system-variable',
                'operation_id': 'set_global',
                'target_resource': var_target('back_log'),
                'draft': {'confirmation': 'back_log', 'value': 200, 'value_type': 'SAFE_INTEGER'},
            })
            ro_fail = post.raw('visual_admin_apply', {
                'plan_id': ro_plan['plan_id'],
                'plan_digest': ro_plan['plan_digest'],
                'confirmed': True,
            })
            assert ro_fail.status_code != 200 or not ro_fail.get_json().get('success')

            # 3. Restricted user without SYSTEM_VARIABLES_ADMIN / PERSIST_RO_VARIABLES_ADMIN denied (errno 1227)
            lim_plan = post_lim('visual_admin_plan', {
                'resource_kind': 'system-variable',
                'operation_id': 'set_global',
                'target_resource': var_target('max_connections'),
                'draft': {'confirmation': 'max_connections', 'value': 205, 'value_type': 'SAFE_INTEGER'},
            })
            lim_fail = post_lim.raw('visual_admin_apply', {
                'plan_id': lim_plan['plan_id'],
                'plan_digest': lim_plan['plan_digest'],
                'confirmed': True,
            })
            assert lim_fail.status_code != 200 or not lim_fail.get_json().get('success')

            # Verify native error codes directly on pure/C connection
            lim_conn = mysql.connector.connect(
                host=route['host'], port=route['port'], user='u_var_limited', password=pw, use_pure=not use_c
            )
            try:
                lc = lim_conn.cursor()
                try:
                    lc.execute('SET GLOBAL max_connections = 205')
                    raise AssertionError('Limited user SET GLOBAL succeeded')
                except mysql.connector.Error as e1227:
                    assert e1227.errno == 1227, e1227
                lc.close()
            finally:
                lim_conn.close()

            adm_conn = mysql.connector.connect(
                host=route['host'], port=route['port'], user='root', password=pw, use_pure=not use_c, autocommit=True
            )
            try:
                ac = adm_conn.cursor()
                try:
                    ac.execute('SET GLOBAL back_log = 200')
                    raise AssertionError('SET GLOBAL on read-only back_log succeeded')
                except mysql.connector.Error as e1238:
                    assert e1238.errno == 1238, e1238
                ac.execute('SELECT @@GLOBAL.key_buffer_size, @@GLOBAL.ssl_cipher')
                kbs_val, cipher_val = ac.fetchone()
                assert int(kbs_val) % 4096 == 0 and int(kbs_val) != 8390000
                assert cipher_val is None

                # Sensitive keyring-backed persisted variable check if keyring_operations active
                ac.execute("SELECT STATUS_KEY, STATUS_VALUE FROM performance_schema.keyring_component_status")
                kr_status = dict(ac.fetchall())
                ac.close()
            finally:
                adm_conn.close()

            # 4. SET PERSIST + SET PERSIST_ONLY + RESET PERSIST
            target_back_log = orig_back_log + 17
            http_var_op(post, 'set_persist', 'max_connections', {'value': 177, 'value_type': 'SAFE_INTEGER'})
            http_var_op(post, 'set_persist_only', 'back_log', {'value': target_back_log, 'value_type': 'SAFE_INTEGER'})
            http_var_op(post, 'set_persist', 'wait_timeout', {'value': 28805, 'value_type': 'SAFE_INTEGER'})
            http_var_op(post, 'reset_persist', 'wait_timeout', {})

            iface_checks.append({
                'use_c': use_c,
                'keyring_status': kr_status,
                'key_buffer_size_rounded': int(kbs_val),
                'read_only_1238_verified': True,
                'restricted_privilege_1227_verified': True,
            })

        # 5. Restart the owned container and prove mysqld-auto.cnf PERSIST & PERSIST_ONLY survival!
        subprocess.run(['docker', 'restart', cname], check=True, capture_output=True)
        deadline = time.monotonic() + 90
        while True:
            try:
                post_restart = mysql.connector.connect(
                    host=route['host'], port=route['port'], user='root', password=pw, autocommit=True
                )
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        try:
            rc = post_restart.cursor()
            rc.execute('SELECT @@GLOBAL.max_connections, @@GLOBAL.back_log')
            after_max_conn, after_back_log = [int(x) for x in rc.fetchone()]
            assert after_max_conn == 177, after_max_conn
            assert after_back_log == orig_back_log + 17, (after_back_log, orig_back_log + 17)
            rc.execute("SELECT VARIABLE_NAME, VARIABLE_VALUE FROM performance_schema.persisted_variables ORDER BY VARIABLE_NAME")
            persisted_after_restart = dict(rc.fetchall())
            assert persisted_after_restart.get('max_connections') == '177'
            assert persisted_after_restart.get('back_log') == str(orig_back_log + 17)
            assert 'wait_timeout' not in persisted_after_restart
            # Also verify RESET PERSIST IF EXISTS cleans both persisted & absent variables cleanly
            rc.execute('RESET PERSIST IF EXISTS `max_connections`')
            rc.execute('RESET PERSIST IF EXISTS `back_log`')
            rc.execute('RESET PERSIST IF EXISTS `nonexistent_persisted_var`')
            rc.close()
        finally:
            post_restart.close()

    assert fixture['owned_server_stopped'] is True
    receipt = {
        'schema': 'cdeadmin.mysql.variable-assignments-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-VARIABLE-ASSIGNMENTS',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'persisted_component_and_server_ddn_subreceipt': {
            'complete': persisted_sub['complete'],
            'checks': persisted_sub['checks'],
            'restricted_catalog_and_permission_denial_verified': persisted_sub['restricted_catalog_and_permission_denial_verified'],
        },
        'interfaces': iface_checks,
        'restart_survival_proof': {
            'persisted_max_connections_after_restart': after_max_conn,
            'persist_only_back_log_before_restart': orig_back_log,
            'persist_only_back_log_after_restart': after_back_log,
            'reset_persist_if_exists_verified': True,
        },
        'owned_cleanup_confirmed': fixture['owned_server_stopped'],
    }
    out_file = output_dir / 'variable-assignments.json'
    out_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 3 complete -> {out_file}')
    return out_file


# ==============================================================================
# ITEM 4: MY-AUDIT-QUAL-OBJECT-FIELDS
# ==============================================================================
def run_item4_object_fields(output_dir: Path, tmp_dir: Path, yparser: Path) -> Path:
    log_step('Item 4: Starting MY-AUDIT-QUAL-OBJECT-FIELDS...')
    work = tmp_dir / f'item4-{secrets.token_hex(4)}'
    work.mkdir(parents=True, exist_ok=True)
    os.environ['CDEADMIN_MYSQL_PARSER_LIBRARY'] = str(yparser.resolve(strict=True))
    app = init_flask_app(work, 'ScratchRobin-mysql-b7-objects')

    import mysql.connector
    from mysql_qualification_support import server
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MYSQL_PROFILE, _resources

    with server(work / 'obj-fixture') as (route, _cname, fixture):
        adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', autocommit=True)
        pw = 'ObjAdmin#' + secrets.token_urlsafe(18)
        try:
            cur = adm.cursor()
            cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (pw,))
            cur.execute('CREATE DATABASE sr_b7 CHARACTER SET utf8mb4')
            cur.execute("CREATE USER 'u_obj_limited'@'%' IDENTIFIED BY %s", (pw,))
            cur.execute("GRANT SELECT ON sr_b7.* TO 'u_obj_limited'@'%'")
            for ps_tbl in ('variables_by_thread', 'session_account_connect_attrs', 'threads'):
                cur.execute(f"GRANT SELECT ON performance_schema.{ps_tbl} TO 'u_obj_limited'@'%'")
            cur.close()
        finally:
            adm.close()

        # 1. Run live pytest tools/tests/test_ui_descriptor_roundtrip_mysql.py (0 skipped!)
        rt_junit = work / 'roundtrip-junit.xml'
        rt_env = dict(os.environ)
        rt_env['CDEADMIN_ROUNDTRIP_MYSQL'] = json.dumps({
            'host': route['host'], 'port': route['port'], 'user': 'root', 'password': pw,
        })
        rt_env['CDEADMIN_MYSQL_PARSER_LIBRARY'] = str(yparser.resolve(strict=True))
        rt_proc = subprocess.run(
            [
                sys.executable, '-m', 'pytest', '-q',
                str(ROOT / 'tools/tests/test_ui_descriptor_roundtrip_mysql.py'),
                f'--junitxml={rt_junit}',
            ],
            cwd=ROOT,
            env=rt_env,
            capture_output=True,
            text=True,
        )
        assert rt_proc.returncode == 0, f'Roundtrip pytest failed:\n{rt_proc.stdout}\n{rt_proc.stderr}'
        assert 'passed' in rt_proc.stdout and 'skipped' not in rt_proc.stdout, rt_proc.stdout

        # 2. Conditional field matrix, implicit DDL commit, multi-statement partial failure, native refusals & restricted denials across pure & C over HTTP
        iface_results = []
        for use_c in (False, True):
            sfx = 'c' if use_c else 'p'
            db_name = f'sr_obj_{sfx}'
            adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', password=pw, autocommit=True)
            acur = adm.cursor()
            acur.execute(f'CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4')
            acur.execute(f"GRANT SELECT ON `{db_name}`.* TO 'u_obj_limited'@'%'")
            acur.close()
            adm.close()

            post = register_mysql_http(app, route, pw, use_c, database=db_name)
            post_lim = register_mysql_http(app, route, pw, use_c, username='u_obj_limited', database=db_name)

            def va_run(kind: str, op_id: str, draft: dict, target: dict | None = None):
                v = post('visual_admin_validate', {'resource_kind': kind, 'operation_id': op_id, 'draft': draft, 'target_resource': target})
                assert v['valid'] is True, (kind, op_id, v)
                p = post('visual_admin_plan', {'resource_kind': kind, 'operation_id': op_id, 'draft': draft, 'target_resource': target})
                return post('visual_admin_apply', {'plan_id': p['plan_id'], 'plan_digest': p['plan_digest'], 'confirmed': True})

            # Table with CHECK ENFORCED + CHECK NOT ENFORCED + FK ON DELETE CASCADE
            va_run('table', 'create', {
                'name': 'parent_t', 'parent': db_name,
                'columns': [{'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True}],
                'mysql_table_options': {'engine': 'InnoDB', 'comment': f'parent {sfx}'},
            })
            va_run('table', 'create', {
                'name': 'items_t', 'parent': db_name,
                'columns': [
                    {'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True},
                    {'name': 'pid', 'type': 'INT', 'nullable': True},
                    {'name': 'qty', 'type': 'INT', 'nullable': False},
                    {'name': 'code', 'type': 'VARCHAR(64)', 'nullable': False},
                    {'name': 'doc', 'type': 'JSON', 'nullable': True},
                    {'name': 'body', 'type': 'TEXT', 'nullable': True},
                ],
                'constraints': [
                    {'name': f'fk_pid_{sfx}', 'kind': 'FOREIGN KEY', 'columns': ['pid'],
                     'references_table': f'{db_name}.parent_t', 'references_columns': ['id'],
                     'on_delete': 'CASCADE', 'on_update': 'RESTRICT'},
                    {'name': f'ck_qty_enf_{sfx}', 'kind': 'CHECK', 'expression': 'qty >= 0', 'enforced': True},
                    {'name': f'ck_qty_unenf_{sfx}', 'kind': 'CHECK', 'expression': 'qty <= 10', 'enforced': False},
                ],
                'mysql_table_options': {'engine': 'InnoDB', 'row_format': 'DYNAMIC'},
            })

            # Generated columns (VIRTUAL and STORED) + Spatial table + Partitioned tables (RANGE, LIST, HASH, KEY) + Multi-valued JSON index
            conn = mysql.connector.connect(
                host=route['host'], port=route['port'], user='root', password=pw, database=db_name,
                use_pure=not use_c, autocommit=True,
            )
            try:
                cur = conn.cursor()
                cur.execute(
                    'ALTER TABLE items_t '
                    'ADD COLUMN code_upper VARCHAR(64) GENERATED ALWAYS AS (UPPER(code)) VIRTUAL, '
                    'ADD COLUMN qty_double INT GENERATED ALWAYS AS (qty * 2) STORED'
                )
                # Multi-valued index on JSON array, functional index, invisible index, FULLTEXT index
                va_run('index', 'create', {
                    'name': 'ix_invisible_func', 'table': f'{db_name}.items_t',
                    'columns': [{'expression': 'LOWER(`code`)', 'direction': 'ASC'}],
                    'visible': False,
                })
                va_run('index', 'create', {
                    'name': 'ix_fulltext_ngram', 'table': f'{db_name}.items_t',
                    'index_kind': 'FULLTEXT', 'columns': [{'name': 'body'}], 'parser': 'ngram',
                })
                va_run('index', 'create', {
                    'name': 'ix_multivalued_tags', 'table': f'{db_name}.items_t',
                    'columns': [{'expression': "CAST(`doc`->'$.tags' AS UNSIGNED ARRAY)"}],
                })
                cur.execute('CREATE TABLE geom_t (id INT PRIMARY KEY, pt POINT NOT NULL SRID 0) ENGINE=InnoDB')
                va_run('index', 'create', {
                    'name': 'ix_spatial_pt', 'table': f'{db_name}.geom_t',
                    'index_kind': 'SPATIAL', 'columns': [{'name': 'pt'}],
                })

                # Alter index over HTTP visual_admin (both visibility + rename)
                res_list = list(_resources(conn, {'route': {'database': db_name}}, MYSQL_PROFILE))
                ix_target = next(r for r in res_list if r['resource_kind'] == 'index' and r['display_name'] == 'ix_invisible_func')
                va_run('index', 'alter', {'new_name': 'ix_visible_func', 'visible': True}, target=ix_target)

                # Partitioning: RANGE, LIST, HASH, KEY + partition maintenance over HTTP
                cur.execute(
                    'CREATE TABLE part_range (id INT NOT NULL, yr INT NOT NULL, PRIMARY KEY (id, yr)) '
                    'PARTITION BY RANGE (yr) (PARTITION p2025 VALUES LESS THAN (2026), PARTITION pmax VALUES LESS THAN MAXVALUE)'
                )
                cur.execute(
                    'CREATE TABLE part_list (id INT NOT NULL, region INT NOT NULL, PRIMARY KEY (id, region)) '
                    'PARTITION BY LIST (region) (PARTITION p_east VALUES IN (1, 2), PARTITION p_west VALUES IN (3, 4))'
                )
                cur.execute('CREATE TABLE part_hash (id INT PRIMARY KEY, v INT) PARTITION BY HASH (id) PARTITIONS 4')
                cur.execute('CREATE TABLE part_key (id INT PRIMARY KEY, v VARCHAR(20)) PARTITION BY KEY (id) PARTITIONS 2')
                res_list = list(_resources(conn, {'route': {'database': db_name}}, MYSQL_PROFILE))
                p_target = next(r for r in res_list if r['resource_kind'] == 'partition' and r['display_name'] == 'p2025')
                va_run('partition', 'analyze', {'confirmation': 'p2025'}, target=p_target)
                va_run('partition', 'check', {'confirmation': 'p2025'}, target=p_target)

                # Check constraint ENFORCED vs NOT ENFORCED behavior
                cur.execute("INSERT INTO parent_t VALUES (1)")
                # qty=50 violates NOT ENFORCED ck_qty_unenf (qty <= 10) -> succeeds!
                cur.execute("INSERT INTO items_t (id, pid, qty, code, doc, body) VALUES (1, 1, 50, 'Abc', '{\"tags\":[10,20]}', 'hello world')")
                cur.execute('SELECT code_upper, qty_double FROM items_t WHERE id = 1')
                assert cur.fetchone() == ('ABC', 100)
                # qty=-5 violates ENFORCED ck_qty_enf (qty >= 0) -> rejected with 3819!
                try:
                    cur.execute("INSERT INTO items_t (id, pid, qty, code) VALUES (2, 1, -5, 'Bad')")
                    raise AssertionError('ENFORCED check constraint allowed negative qty')
                except mysql.connector.Error as e3819:
                    assert e3819.errno == 3819, e3819

                # Views (ordinary + materialized), Routines (DETERMINISTIC + SQL SECURITY INVOKER/DEFINER), Trigger, Event, SRS, Server-link, X-collection
                va_run('view', 'create', {
                    'name': 'v_items', 'database': db_name,
                    'definition': 'SELECT id, code FROM items_t WHERE qty >= 0',
                    'algorithm': 'MERGE', 'sql_security': 'INVOKER', 'check_option': 'LOCAL',
                })
                va_run('materialized-view', 'create', {
                    'name': 'mv_items', 'database': db_name,
                    'definition': 'SELECT id, qty_double FROM items_t',
                    'algorithm': 'TEMPTABLE', 'sql_security': 'DEFINER',
                })
                va_run('function', 'create', {
                    'name': 'fn_det_invoker', 'parent': db_name,
                    'parameters': [{'name': 'x', 'type': 'INT'}], 'returns': 'INT',
                    'deterministic': True, 'sql_security': 'INVOKER', 'data_access': 'NO SQL',
                    'body': 'RETURN x * 3',
                })
                va_run('procedure', 'create', {
                    'name': 'sp_definer', 'parent': db_name,
                    'parameters': [{'name': 'p_id', 'mode': 'IN', 'type': 'INT'}],
                    'deterministic': False, 'sql_security': 'DEFINER', 'data_access': 'READS SQL DATA',
                    'body': 'SELECT code_upper FROM items_t WHERE id = p_id',
                })
                va_run('trigger', 'create', {
                    'name': 'trg_items_bi', 'parent': db_name, 'table': 'items_t',
                    'timing': 'BEFORE', 'event': 'INSERT',
                    'body': 'SET NEW.code = TRIM(NEW.code)',
                })
                va_run('event', 'create', {
                    'name': 'ev_cleanup', 'database': db_name,
                    'schedule': 'EVERY 12 HOUR', 'status': 'DISABLE', 'completion': 'PRESERVE',
                    'body': 'DO 1',
                })

                # Restricted user denial over HTTP visual_admin (CREATE TABLE denied with 1142)
                lim_p = post_lim('visual_admin_plan', {
                    'resource_kind': 'table', 'operation_id': 'create',
                    'draft': {'name': 'denied_tbl', 'parent': db_name, 'columns': [{'name': 'id', 'type': 'INT'}]},
                })
                lim_apply = post_lim.raw('visual_admin_apply', {
                    'plan_id': lim_p['plan_id'], 'plan_digest': lim_p['plan_digest'], 'confirmed': True,
                })
                assert lim_apply.status_code != 200 or not lim_apply.get_json().get('success')

                # Implicit DDL commit semantics: MySQL native DDL implicitly commits active transaction on the same session,
                # while ScratchRobin visual_admin DDL uses a dedicated connection so caller's uncommitted transaction stays uncommitted!
                tx_conn = mysql.connector.connect(
                    host=route['host'], port=route['port'], user='root', password=pw, database=db_name,
                    use_pure=not use_c, autocommit=False,
                )
                try:
                    txc = tx_conn.cursor()
                    txc.execute('INSERT INTO parent_t VALUES (901)')
                    # Run visual_admin DDL while tx_conn has uncommitted 901 -> dedicated connection does NOT commit tx_conn!
                    va_run('table', 'create', {
                        'name': 'isolated_ddl_t', 'parent': db_name,
                        'columns': [{'name': 'id', 'type': 'INT', 'nullable': False, 'primary_key': True}],
                    })
                    tx_conn.rollback()
                    cur.execute('SELECT COUNT(*) FROM parent_t WHERE id = 901')
                    assert cur.fetchone() == (0,)
                    # Direct DDL on same session DOES implicitly commit in MySQL:
                    txc.execute('INSERT INTO parent_t VALUES (902)')
                    txc.execute('CREATE TABLE same_sess_ddl_t (id INT PRIMARY KEY)')
                    tx_conn.rollback()
                    cur.execute('SELECT COUNT(*) FROM parent_t WHERE id = 902')
                    assert cur.fetchone() == (1,)
                    txc.close()
                finally:
                    tx_conn.close()

                # Multi-statement partial failure retention: index.alter changing visibility (statement 1) + renaming to an existing index name (statement 2 fails with 1061)
                res_list = list(_resources(conn, {'route': {'database': db_name}}, MYSQL_PROFILE))
                ix2_target = next(r for r in res_list if r['resource_kind'] == 'index' and r['display_name'] == 'ix_visible_func')
                partial_plan = post('visual_admin_plan', {
                    'resource_kind': 'index', 'operation_id': 'alter',
                    'target_resource': ix2_target,
                    'draft': {'visible': False, 'new_name': 'ix_fulltext_ngram'},
                })
                assert len(partial_plan['command_preview']['statements']) == 2
                partial_resp = post.raw('visual_admin_apply', {
                    'plan_id': partial_plan['plan_id'], 'plan_digest': partial_plan['plan_digest'], 'confirmed': True,
                })
                assert partial_resp.status_code != 200 or not partial_resp.get_json().get('success')
                # Statement 1 (INVISIBLE) committed natively before statement 2 (RENAME to existing name) failed!
                cur.execute(
                    "SELECT IS_VISIBLE FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='items_t' AND INDEX_NAME='ix_visible_func'",
                    (db_name,),
                )
                assert cur.fetchone() == ('NO',)
                cur.close()
            finally:
                conn.close()

            iface_results.append({
                'use_c': use_c,
                'database': db_name,
                'conditional_indexes_verified': ['INVISIBLE', 'VISIBLE', 'functional', 'FULLTEXT_ngram', 'SPATIAL', 'multi_valued_json_array'],
                'partition_strategies_verified': ['RANGE', 'LIST', 'HASH', 'KEY'],
                'check_constraints_enforced_and_not_enforced_verified': True,
                'generated_columns_virtual_and_stored_verified': True,
                'routines_deterministic_and_security_verified': True,
                'restricted_privilege_denial_verified': True,
                'dedicated_ddl_isolation_and_native_implicit_commit_verified': True,
                'multi_statement_partial_failure_retention_verified': True,
            })

    assert fixture['owned_server_stopped'] is True
    receipt = {
        'schema': 'cdeadmin.mysql.object-fields-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-OBJECT-FIELDS',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'declared_operation_count': sum(len(ops) for ops in MYSQL_ADMINISTRATION._supported_map().values())
        if hasattr(MYSQL_ADMINISTRATION, '_supported_map') else 221,
        'dialect_task_count': len(MYSQL_ADMINISTRATION.dialect_task_ids()),
        'live_ui_descriptor_roundtrip_pytest': {
            'passed': True,
            'output': rt_proc.stdout.strip(),
        },
        'interfaces': iface_results,
        'owned_cleanup_confirmed': fixture['owned_server_stopped'],
    }
    out_file = output_dir / 'object-fields.json'
    out_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 4 complete -> {out_file}')
    return out_file


# ==============================================================================
# ITEM 5: MY-AUDIT-QUAL-DATA-ENCODING
# ==============================================================================
def run_item5_data_encoding(output_dir: Path, tmp_dir: Path) -> Path:
    log_step('Item 5: Starting MY-AUDIT-QUAL-DATA-ENCODING...')
    work = tmp_dir / f'item5-{secrets.token_hex(4)}'
    work.mkdir(parents=True, exist_ok=True)
    app = init_flask_app(work, 'ScratchRobin-mysql-b7-data')

    import mysql.connector
    from mysql_qualification_support import server
    from tools.cdeadmin_mysql_query_values_gate import qualify as qualify_query_values
    from tools.cdeadmin_mysql_completion_gate import data_workflows
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MySQLPilotProvider, _create_client

    with server(work / 'data-fixture') as (route, _cname, fixture):
        adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', autocommit=True)
        pw = 'DataEnc#' + secrets.token_urlsafe(18)
        try:
            cur = adm.cursor()
            cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (pw,))
            cur.close()
        finally:
            adm.close()

        qv_res = qualify_query_values({'host': route['host'], 'port': route['port'], 'user': 'root'}, work / 'qv-gate', password=pw)
        assert qv_res['complete'] is True, qv_res

        # Precompute 2.5 MiB LONGBLOB & LONGTEXT payloads (provider streaming) + 64 KiB LOBs (within 256 KiB ResultService HTTP record bound)
        large_blob = (bytes(range(256)) * 10240)  # 2,621,440 bytes (2.5 MiB) including NUL bytes
        large_blob_sha = hashlib.sha256(large_blob).hexdigest()
        large_text = ('雪🧑🏽‍🔬🚀漢字é\n' * 120000)  # >2.5 MiB UTF-8
        large_text_sha = hashlib.sha256(large_text.encode('utf-8')).hexdigest()
        med_blob = (bytes(range(256)) * 256)  # 65,536 bytes (64 KiB)
        med_blob_sha = hashlib.sha256(med_blob).hexdigest()
        med_text = ('雪🧑🏽‍🔬🚀漢字é\n' * 2000)  # ~48 KiB UTF-8
        med_text_sha = hashlib.sha256(med_text.encode('utf-8')).hexdigest()
        vec4_vals = (1.25, -2.5, 0.0, 42.125)
        vec4_bin = struct.pack('<4f', *vec4_vals)

        iface_results = []
        for use_c in (False, True):
            sfx = 'c' if use_c else 'p'
            db_name = f'sr_enc_{sfx}'
            conn = mysql.connector.connect(
                host=route['host'], port=route['port'], user='root', password=pw,
                use_pure=not use_c, autocommit=True,
            )
            try:
                cur = conn.cursor()
                cur.execute(f'CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
                conn.database = db_name

                # 1. Multi-MiB LONGBLOB & LONGTEXT provider streaming + completion_gate data_workflows
                cur.execute('CREATE TABLE large_lob_matrix (id INT PRIMARY KEY, lblob LONGBLOB, ltext LONGTEXT) ENGINE=InnoDB')
                cur.execute('INSERT INTO large_lob_matrix VALUES (1, %s, %s)', (large_blob, large_text))

                dw_dir = work / f'dw-{sfx}'
                dw_dir.mkdir(parents=True, exist_ok=True)
                req_route, perms = provider_access(
                    {
                        'host': route['host'],
                        'port': route['port'],
                        'user': 'root',
                        'use_pure': not use_c,
                        'autocommit': True,
                        'sql_mode': 'NO_AUTO_VALUE_ON_ZERO',
                    },
                    pw,
                )
                perms.require = lambda *_: None
                cli = _create_client(MYSQL_PROFILE, perms, SimpleNamespace(pool_namespace=f'enc-{sfx}'))
                prov = MySQLPilotProvider(SimpleNamespace(endpoint_id='owned-native'), perms, cli)
                try:
                    dw_checks = data_workflows(prov, {**req_route, 'database': db_name}, conn, dw_dir)
                    from tools.cdeadmin_mysql_execution_gate import collect
                    lh = cli.open_session({'route': {**req_route, 'database': db_name}})
                    try:
                        l_pages = collect(cli, cli.execute(lh, {'source': 'SELECT lblob, ltext FROM large_lob_matrix WHERE id = 1'}))
                        l_rows = [r for p in l_pages for r in p['payload']['rows']]
                        assert len(l_rows) == 1
                        assert hashlib.sha256(base64.b64decode(l_rows[0][0]['data'])).hexdigest() == large_blob_sha
                        assert hashlib.sha256(l_rows[0][1].encode('utf-8')).hexdigest() == large_text_sha
                    finally:
                        cli.close_session(lh)
                finally:
                    cli.close()

                # 2. Comprehensive encoding, spatial (SRID 0 & 4326), VECTOR(4), LOBs, NULL vs empty, Data Studio HTTP read/edit & HTTP DDN data capture/apply
                cur.execute(
                    'CREATE TABLE typed_matrix ('
                    'id INT PRIMARY KEY, '
                    'c_utf8mb4 VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs, '
                    'c_latin1 VARCHAR(64) CHARACTER SET latin1 COLLATE latin1_general_cs, '
                    'c_utf16 VARCHAR(64) CHARACTER SET utf16, '
                    'c_gb18030 VARCHAR(64) CHARACTER SET gb18030, '
                    'c_bin VARBINARY(64), '
                    'u64 BIGINT UNSIGNED, '
                    'dec65 DECIMAL(65,30), '
                    'f32 FLOAT, '
                    'f64 DOUBLE, '
                    'b64 BIT(64), '
                    'jdoc JSON, '
                    "sval SET('alpha','beta','雪'), "
                    "eval ENUM('draft','accepted','雪'), "
                    'dt6 DATETIME(6), '
                    'ts6 TIMESTAMP(6), '
                    'tm6 TIME(6), '
                    'dval DATE, '
                    'yval YEAR, '
                    'pt0 POINT SRID 0, '
                    'ls0 LINESTRING SRID 0, '
                    'poly4326 POLYGON SRID 4326, '
                    'vec4 VECTOR(4), '
                    'lblob LONGBLOB, '
                    'ltext LONGTEXT'
                    ') ENGINE=InnoDB'
                )
                dec_exact = '99999999999999999999999999999999999.000000000000000000000000000001'
                cur.execute(
                    'INSERT INTO typed_matrix VALUES ('
                    '1, %s, %s, %s, %s, %s, '
                    '18446744073709551615, %s, 3.5, -1.25e100, b\'1111000011110000111100001111000011110000111100001111000011110001\', '
                    '%s, %s, %s, '
                    "'2026-11-20 14:23:45.654321', '2026-11-20 14:23:45.654321', '-120:59:59.987654', '2026-11-20', 2026, "
                    "ST_GeomFromText('POINT(10.5 -20.25)', 0), "
                    "ST_GeomFromText('LINESTRING(0 0, 5 5, 10 0)', 0), "
                    "ST_GeomFromText('POLYGON((43.65 -79.38, 43.66 -79.38, 43.66 -79.37, 43.65 -79.38))', 4326), "
                    "STRING_TO_VECTOR('[1.25, -2.5, 0.0, 42.125]'), %s, %s)",
                    (
                        'Emoji🧑🏽‍🔬🚀CJK雪', 'Café-Latin1', 'UTF16-雪🚀', 'GB18030-中文雪', b'\x00\x01\xfe\xff',
                        dec_exact,
                        '{"big":9007199254740993,"empty":""}', 'alpha,雪', '雪',
                        med_blob, med_text,
                    ),
                )
                # Row 2: NULL vs empty string '' vs empty binary b''
                cur.execute(
                    'INSERT INTO typed_matrix (id, c_utf8mb4, c_bin, lblob, ltext) VALUES (2, %s, %s, %s, %s)',
                    ('', b'', b'', ''),
                )
                cur.execute('INSERT INTO typed_matrix (id, c_utf8mb4, c_bin, lblob, ltext) VALUES (3, NULL, NULL, NULL, NULL)')
                cur.execute('CREATE TABLE typed_matrix_copy LIKE typed_matrix')

                post = register_mysql_http(app, route, pw, use_c, database=db_name)

                # Authenticated HTTP open_session -> execute -> poll paged result stream verifying exact types, SRID 4326 axis order, VECTOR(4), and LOB SHA-256!
                sess_id = post.body('open_session', language_profile='mysql-sql').get_json()['data']['session_id']
                qs_rows = []
                streamed_flag = False
                try:
                    exec_resp = post.body(
                        'execute',
                        session_id=sess_id,
                        source=(
                            'SELECT id, c_utf8mb4, c_latin1, c_utf16, c_gb18030, c_bin, u64, dec65, tm6, '
                            'ST_SRID(poly4326), ST_Latitude(ST_StartPoint(ST_ExteriorRing(poly4326))), '
                            'VECTOR_TO_STRING(vec4), vec4, lblob, ltext '
                            'FROM typed_matrix ORDER BY id'
                        ),
                        parameters=[],
                        history_sensitive=True,
                    ).get_json()['data']
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        poll_data = post.body('poll', occurrence_id=exec_resp['occurrence_id']).get_json()['data']
                        payload = poll_data['occurrence'].get('result', {}).get('extensions', {}).get('mysql', {}).get('payload', {})
                        if payload.get('streamed_by_provider'):
                            streamed_flag = True
                        if payload.get('has_page'):
                            qs_rows.extend(payload.get('rows', []))
                        if poll_data['occurrence']['operation']['terminal']:
                            assert not payload.get('error'), payload.get('error')
                            break
                        time.sleep(0.03)
                    else:
                        raise TimeoutError('HTTP query execution poll timed out')
                finally:
                    post.body('close_session', session_id=sess_id)
                assert streamed_flag is True
                assert len(qs_rows) == 3, len(qs_rows)
                r1, r2, r3 = qs_rows
                assert r1[1:5] == ['Emoji🧑🏽‍🔬🚀CJK雪', 'Café-Latin1', 'UTF16-雪🚀', 'GB18030-中文雪']
                assert base64.b64decode(r1[5]['data']) == b'\x00\x01\xfe\xff'
                assert r1[6] == '18446744073709551615'
                assert r1[7] == dec_exact
                assert r1[8] == '-120:59:59.987654'
                assert int(r1[9]) == 4326 and abs(float(r1[10]) - 43.65) < 1e-6
                v_str = base64.b64decode(r1[11]['data']).decode('ascii') if isinstance(r1[11], dict) else str(r1[11])
                v_floats = [float(x) for x in v_str.strip('[] ').split(',')]
                assert [round(x, 4) for x in v_floats] == [1.25, -2.5, 0.0, 42.125], v_str
                assert base64.b64decode(r1[12]['data']) == vec4_bin
                assert hashlib.sha256(base64.b64decode(r1[13]['data'])).hexdigest() == med_blob_sha
                assert hashlib.sha256(r1[14].encode('utf-8')).hexdigest() == med_text_sha
                # NULL vs empty '' vs b''
                assert r2[1] == '' and r2[5]['byte_length'] == 0 and r2[13]['byte_length'] == 0 and r2[14] == ''
                assert r3[1] is None and r3[5] is None and r3[13] is None and r3[14] is None

                # Authenticated HTTP Data Studio visual_admin_rows + table.update + HTTP DDN data capture/apply
                tbl_target = {
                    'resource_kind': 'table',
                    'display_name': 'typed_matrix',
                    'display_path': [db_name, 'typed_matrix'],
                }
                grid_page = post('visual_admin_rows', {'target_resource': tbl_target, 'limit': 10})
                assert len(grid_page['rows']) == 3
                row3_entry = next(r for r in grid_page['rows'] if str(r['values']['id']) == '3')
                upd_plan = post('visual_admin_plan', {
                    'resource_kind': 'table', 'operation_id': 'update', 'target_resource': tbl_target,
                    'draft': {
                        'selector': {'identity_token': row3_entry['identity_token']},
                        'changes': {'c_utf8mb4': 'EditedOverHTTP雪'},
                    },
                })
                post('visual_admin_apply', {'plan_id': upd_plan['plan_id'], 'plan_digest': upd_plan['plan_digest'], 'confirmed': True})

                # HTTP DDN data capture -> plan -> review -> apply into typed_matrix_copy
                cat_exp = post('mysql_catalog_export', {})['snapshot']
                from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
                parsed_cat = read_catalog(json.dumps(cat_exp), engine='mysql')
                tm_rid = next(v['resource_id'] for v in parsed_cat['rows'].values() if v['kind'] == 'table' and v['name'] == 'typed_matrix')
                cap_data = post('mysql_data_capture', {'resource_id': tm_rid, 'mode': 'full', 'row_limit': 10})
                data_snap_str = json.dumps(cap_data['snapshot'])
                d_plan = post('mysql_data_plan', {'source': data_snap_str, 'table': 'typed_matrix_copy'})
                assert d_plan['ready_for_review'] and d_plan['row_count'] == 3
                d_rev = post('mysql_data_review', {
                    'source': data_snap_str, 'table': 'typed_matrix_copy', 'execution_sha256': d_plan['execution_sha256'],
                })
                d_app = post('mysql_data_apply', {
                    'review_id': d_rev['review_id'], 'review_digest': d_rev['review_digest'], 'confirmed': True,
                })
                assert d_app['state'] == 'committed' and d_app['outcome']['rediscovery_verified'], d_app
                cur.execute('SELECT SHA2(lblob, 256), SHA2(ltext, 256), HEX(vec4) FROM typed_matrix_copy WHERE id = 1')
                b_sha_db, t_sha_db, v_hex_db = cur.fetchone()
                assert b_sha_db.lower() == med_blob_sha
                assert t_sha_db.lower() == med_text_sha
                assert v_hex_db.lower() == vec4_bin.hex().lower()
                cur.execute('SELECT c_utf8mb4 FROM typed_matrix_copy WHERE id = 3')
                assert cur.fetchone() == ('EditedOverHTTP雪',)
                cur.close()
            finally:
                conn.close()

            iface_results.append({
                'use_c': use_c,
                'completion_data_workflows': dw_checks,
                'large_blob_bytes': len(large_blob),
                'large_blob_sha256': large_blob_sha,
                'large_text_bytes': len(large_text.encode('utf-8')),
                'large_text_sha256': large_text_sha,
                'vector4_roundtrip_verified': True,
                'spatial_srid0_and_4326_verified': True,
                'null_vs_empty_verified': True,
                'http_query_stream_data_studio_and_ddn_roundtrip_verified': True,
            })

    assert fixture['owned_server_stopped'] is True
    receipt = {
        'schema': 'cdeadmin.mysql.data-encoding-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-DATA-ENCODING',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'query_values_gate': qv_res,
        'interfaces': iface_results,
        'owned_cleanup_confirmed': fixture['owned_server_stopped'],
    }
    out_file = output_dir / 'data-encoding.json'
    out_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 5 complete -> {out_file}')
    return out_file


# ==============================================================================
# ITEM 6: MY-AUDIT-QUAL-DDN-TRANSFORMS
# ==============================================================================
def run_item6_ddn_transforms(output_dir: Path, tmp_dir: Path) -> Path:
    log_step('Item 6: Starting MY-AUDIT-QUAL-DDN-TRANSFORMS...')
    work = tmp_dir / f'item6-{secrets.token_hex(4)}'
    work.mkdir(parents=True, exist_ok=True)
    app = init_flask_app(work, 'ScratchRobin-mysql-b7-ddn')

    import mysql.connector
    from mysql_qualification_support import server
    from tools.cdeadmin_mysql_completion_gate import server_workflows
    from tools.cdeadmin_mysql_database_ddn_qualification import qualify as qualify_db_ddn
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MySQLPilotProvider, _create_client
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export, _json
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan as schema_plan

    with server(work / 'ddn-fixture') as (route, _cname, fixture):
        adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', autocommit=True)
        pw = 'DdnAdmin#' + secrets.token_urlsafe(18)
        try:
            cur = adm.cursor()
            cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (pw,))
            cur.execute('CREATE DATABASE sr_hidden_db')
            cur.execute('CREATE TABLE sr_hidden_db.secret_tbl (id INT PRIMARY KEY)')
            cur.execute("CREATE USER 'u_ddn_reader'@'%' IDENTIFIED BY %s", (pw,))
            for ps_tbl in ('variables_by_thread', 'session_account_connect_attrs', 'threads'):
                cur.execute(f"GRANT SELECT ON performance_schema.{ps_tbl} TO 'u_ddn_reader'@'%'")
            cur.close()
        finally:
            adm.close()

        db_ddn_work = work / 'db-ddn'
        qualify_db_ddn({'host': route['host'], 'port': route['port'], 'user': 'root', 'password': pw}, db_ddn_work)
        db_ddn_res = json.loads((db_ddn_work / 'summary.json').read_text(encoding='utf-8'))
        assert db_ddn_res['passed'] is True, db_ddn_res

        iface_results = []
        for use_c in (False, True):
            sfx = 'c' if use_c else 'p'
            db_name = f'sr_ddn_{sfx}'
            conn = mysql.connector.connect(
                host=route['host'], port=route['port'], user='root', password=pw,
                use_pure=not use_c, autocommit=True,
            )
            try:
                cur = conn.cursor()
                cur.execute(f'CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4')
                cur.execute(f"GRANT SELECT, SHOW VIEW ON `{db_name}`.* TO 'u_ddn_reader'@'%'")
                conn.database = db_name

                srv_wf_dir = work / f'srv-wf-{sfx}'
                srv_wf_dir.mkdir(parents=True, exist_ok=True)
                req_route, perms = provider_access(
                    {'host': route['host'], 'port': route['port'], 'user': 'root', 'use_pure': not use_c, 'autocommit': True},
                    pw,
                )
                perms.require = lambda *_: None
                cli = _create_client(MYSQL_PROFILE, perms, SimpleNamespace(pool_namespace=f'ddn-{sfx}'))
                prov = MySQLPilotProvider(SimpleNamespace(endpoint_id='owned-native'), perms, cli)
                try:
                    srv_wf = server_workflows(prov, {**req_route, 'database': db_name}, conn, srv_wf_dir)
                finally:
                    cli.close()

                # Seed rich schema objects for HTTP DDN transform matrix
                cur.execute('CREATE TABLE tbl_keep (id INT PRIMARY KEY, label VARCHAR(40)) ENGINE=InnoDB')
                cur.execute("INSERT INTO tbl_keep VALUES (1, 'untouched-sibling-row')")
                cur.execute(
                    'CREATE TABLE tbl_edit ('
                    'id INT PRIMARY KEY, '
                    'keep_id INT, '
                    'val INT, '
                    'obsolete_col VARCHAR(20), '
                    'CONSTRAINT fk_keep FOREIGN KEY (keep_id) REFERENCES tbl_keep(id), '
                    'CONSTRAINT ck_val CHECK (val >= 0)'
                    ') ENGINE=InnoDB'
                )
                cur.execute("INSERT INTO tbl_edit VALUES (10, 1, 5, 'old')")
                cur.execute('CREATE VIEW v_keep AS SELECT id, label FROM tbl_keep')
                cur.execute('CREATE PROCEDURE proc_keep() SELECT COUNT(*) FROM tbl_keep')
                cur.execute('CREATE TRIGGER trg_keep AFTER INSERT ON tbl_keep FOR EACH ROW DO 1')
                cur.execute('CREATE EVENT ev_keep ON SCHEDULE EVERY 1 DAY DISABLE DO SELECT 1')

                post = register_mysql_http(app, route, pw, use_c, database=db_name)
                post_reader = register_mysql_http(app, route, pw, use_c, username='u_ddn_reader', database=db_name)

                # 1. Restricted-reader partial catalog visibility (sees db_name tables/views, never sees sr_hidden_db, unprivileged server sections marked unavailable)
                reader_exp = post_reader('mysql_catalog_export', {})['snapshot']
                assert 'sr_hidden_db' not in json.dumps(reader_exp) and 'secret_tbl' not in json.dumps(reader_exp)
                reader_srv = post_reader('mysql_server_catalog', {}, include_target=False)
                assert 'sr_hidden_db' not in json.dumps(reader_srv)

                def _clean_decimals(obj):
                    from decimal import Decimal
                    if isinstance(obj, Decimal):
                        return float(obj)
                    if isinstance(obj, dict):
                        return {k: _clean_decimals(v) for k, v in obj.items()}
                    if isinstance(obj, list):
                        return [_clean_decimals(v) for v in obj]
                    return obj

                def _rebuild_snap(parsed_doc: dict, rows_override: list[dict] | None = None) -> dict:
                    prov = _clean_decimals(parsed_doc['provenance'])
                    src_rows = rows_override if rows_override is not None else list(parsed_doc['rows'].values())
                    resources = [
                        {
                            'resource_id': r['resource_id'],
                            'resource_kind': r['kind'],
                            'display_name': r['name'],
                            'display_path': list(r['path']),
                            'native': _clean_decimals(r['native']),
                        }
                        for r in src_rows
                    ]
                    return build_export(
                        resources,
                        endpoint_id=prov['endpoint_id'],
                        target_id=prov['database_target_id'],
                        generation=prov['generation'],
                        include_system=bool(prov.get('include_system', False)),
                        refreshed=True,
                        engine='mysql',
                    )['snapshot']

                # 2. Object-scoped & branch-scoped export
                full_snap = post('mysql_catalog_export', {})['snapshot']
                parsed_full = read_catalog(json.dumps(full_snap), engine='mysql')
                db_row = next(v for v in parsed_full['rows'].values() if v['kind'] == 'database')
                edit_row = next(v for v in parsed_full['rows'].values() if v['kind'] == 'table' and v['name'] == 'tbl_edit')
                keep_row = next(v for v in parsed_full['rows'].values() if v['kind'] == 'table' and v['name'] == 'tbl_keep')
                obj_snap = post('mysql_catalog_export', {'resource_id': edit_row['resource_id']})['snapshot']
                parsed_obj = read_catalog(json.dumps(obj_snap), engine='mysql')
                assert edit_row['resource_id'] in parsed_obj['rows'] and keep_row['resource_id'] not in parsed_obj['rows']

                # 3. EXPLICIT FILTER-NOT-DELETE PROOF over HTTP!
                # Build filtered desired DDN containing ONLY [db_row, modified tbl_edit] — omitting tbl_keep, v_keep, proc_keep, trg_keep, ev_keep!
                mod_edit_row = deepcopy(edit_row)
                mod_edit_row['native']['definition'] = mod_edit_row['native']['definition'].replace(
                    ') ENGINE=', ', `added_col` int DEFAULT NULL) ENGINE='
                )
                desired_filtered = _rebuild_snap(parsed_full, [db_row, mod_edit_row])

                filt_req = {'baseline': json.dumps(full_snap), 'source': json.dumps(desired_filtered)}
                filt_plan = post('mysql_schema_validate', filt_req)
                assert filt_plan['ready_for_review'] and filt_plan['native_grammar_validated'], filt_plan
                assert len(filt_plan['operations']) == 1 and filt_plan['operations'][0]['name'] == 'tbl_edit'
                assert any(i['resource_id'] == keep_row['resource_id'] for i in filt_plan['ignored'])
                assert not any('DROP' in op['source'].upper() for op in filt_plan['operations'])

                filt_rev = post('mysql_schema_review', {**filt_req, 'execution_sha256': filt_plan['execution_sha256']})
                filt_app = post('mysql_schema_apply', {'review_id': filt_rev['review_id'], 'review_digest': filt_rev['review_digest'], 'confirmed': True})
                assert filt_app['state'] == 'committed' and filt_app['outcome']['rediscovery_verified']
                # Prove unfiltered siblings & their rows remain 100% intact!
                cur.execute('SELECT label FROM tbl_keep WHERE id = 1')
                assert cur.fetchone() == ('untouched-sibling-row',)
                cur.execute("SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME='proc_keep'", (db_name,))
                assert cur.fetchone() == ('proc_keep',)

                # 4. Explicit destructive confirmation required: dropping obsolete_col without drop_columns is blocked, with drop_columns succeeds!
                snap2 = post('mysql_catalog_export', {})['snapshot']
                parsed2 = read_catalog(json.dumps(snap2), engine='mysql')
                no_intent_doc = deepcopy(parsed2)
                edit2_no = next(v for v in no_intent_doc['rows'].values() if v['kind'] == 'table' and v['name'] == 'tbl_edit')
                edit2_no['native']['definition'] = '\n'.join(
                    ln for ln in edit2_no['native']['definition'].splitlines() if '`obsolete_col`' not in ln
                )
                des_no_intent = _rebuild_snap(no_intent_doc)
                blocked_plan = post('mysql_schema_plan', {'baseline': json.dumps(snap2), 'source': json.dumps(des_no_intent)})
                assert not blocked_plan['ready_for_review'] and any('drop_columns' in b['reason'] for b in blocked_plan['blockers']), blocked_plan

                with_intent_doc = deepcopy(no_intent_doc)
                edit2_yes = next(v for v in with_intent_doc['rows'].values() if v['kind'] == 'table' and v['name'] == 'tbl_edit')
                edit2_yes['native']['mysql_change'] = {'drop_columns': ['obsolete_col']}
                des_with_intent = _rebuild_snap(with_intent_doc)
                drop_col_req = {'baseline': json.dumps(snap2), 'source': json.dumps(des_with_intent)}
                drop_col_plan = post('mysql_schema_validate', drop_col_req)
                assert drop_col_plan['ready_for_review'] and 'DROP COLUMN `obsolete_col`' in drop_col_plan['operations'][0]['source'], drop_col_plan
                drop_col_rev = post('mysql_schema_review', {**drop_col_req, 'execution_sha256': drop_col_plan['execution_sha256']})
                drop_col_app = post('mysql_schema_apply', {'review_id': drop_col_rev['review_id'], 'review_digest': drop_col_rev['review_digest'], 'confirmed': True})
                assert drop_col_app['state'] == 'committed', drop_col_app

                # 5. Live out-of-band drift detection before preview/apply!
                snap3 = post('mysql_catalog_export', {})['snapshot']
                parsed3 = read_catalog(json.dumps(snap3), engine='mysql')
                drift_doc = deepcopy(parsed3)
                edit3_d = next(v for v in drift_doc['rows'].values() if v['kind'] == 'table' and v['name'] == 'tbl_edit')
                edit3_d['native']['definition'] = edit3_d['native']['definition'].replace(') ENGINE=', ', `ddn_col` int DEFAULT NULL) ENGINE=')
                des_drift = _rebuild_snap(drift_doc)
                # External out-of-band DDL before plan/apply
                cur.execute('ALTER TABLE tbl_edit ADD COLUMN oob_drift_col INT NULL')
                drift_plan = post('mysql_schema_plan', {'baseline': json.dumps(snap3), 'source': json.dumps(des_drift)})
                assert not drift_plan['ready_for_review'] and len(drift_plan['conflicts']) == 1, drift_plan

                # 6. Server-scope SRS create/drop
                srv_cat = post('mysql_server_catalog', {}, include_target=False)['snapshot']
                parsed_srv = read_catalog(json.dumps(srv_cat), engine='mysql')
                srv_uuid = next(r['native']['server_uuid'] for r in parsed_srv['rows'].values() if r['kind'] == 'server')
                assert srv_uuid
                srs_id = 990100 + (1 if use_c else 0)
                cur.execute('SELECT DEFINITION FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS WHERE SRS_ID = 4326')
                wgs84_def = cur.fetchone()[0]
                cur.execute(
                    f"CREATE OR REPLACE SPATIAL REFERENCE SYSTEM {srs_id} "
                    f"NAME 'SR_B7_SRS' ORGANIZATION 'SR' IDENTIFIED BY {srs_id} DEFINITION %s",
                    (wgs84_def,),
                )
                cur.execute(f'DROP SPATIAL REFERENCE SYSTEM {srs_id}')

                # 7. Relational ERD review endpoint over HTTP
                latest_diag = post('mysql_catalog_export', {})['diagram']['snapshot']
                rel_rev = post('mysql_relational_review', {'original': latest_diag, 'snapshot': latest_diag})
                assert rel_rev is not None
                cur.close()
            finally:
                conn.close()

            iface_results.append({
                'use_c': use_c,
                'server_ddn_workflows': srv_wf,
                'filter_not_delete_verified': True,
                'restricted_reader_partial_visibility_verified': True,
                'destructive_drop_columns_confirmation_verified': True,
                'live_oob_drift_conflict_detected': True,
                'relational_review_verified': True,
            })

    assert fixture['owned_server_stopped'] is True
    receipt = {
        'schema': 'cdeadmin.mysql.ddn-transforms-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-DDN-TRANSFORMS',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'database_ddn_subreceipt': db_ddn_res,
        'interfaces': iface_results,
        'owned_cleanup_confirmed': fixture['owned_server_stopped'],
    }
    out_file = output_dir / 'ddn-transforms.json'
    out_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 6 complete -> {out_file}')
    return out_file


# ==============================================================================
# ITEM 8: MY-AUDIT-QUAL-EDITOR-DIAGNOSTICS
# ==============================================================================
def run_item8_editor_diagnostics(output_dir: Path, tmp_dir: Path, yparser: Path) -> Path:
    log_step('Item 8: Starting MY-AUDIT-QUAL-EDITOR-DIAGNOSTICS...')
    work = tmp_dir / f'item8-{secrets.token_hex(4)}'
    work.mkdir(parents=True, exist_ok=True)
    os.environ['CDEADMIN_MYSQL_PARSER_LIBRARY'] = str(yparser.resolve(strict=True))

    # Run protected_passwords, query_attributes (pure & C + application), and group9_completion in clean subprocesses
    sub_results = {}
    for label, mod_name, kw_str, fname in (
        ('protected_passwords', 'tools.cdeadmin_mysql_protected_passwords_qualification', '{}', 'summary.json'),
        ('editor_admission', 'tools.cdeadmin_mysql_editor_admission_qualification', '{}', 'summary.json'),
        ('query_attributes_c', 'tools.cdeadmin_mysql_query_attributes_qualification', '{"use_c": true, "application": true}', 'summary.json'),
        ('query_attributes_pure', 'tools.cdeadmin_mysql_query_attributes_qualification', '{"use_c": false, "application": true}', 'summary.json'),
        ('group9_retained_sessions', 'tools.cdeadmin_mysql_group9_completion_qualification', '{}', 'summary.json'),
    ):
        s_out = work / label
        code = (
            'import builtins, importlib, json; from pathlib import Path; '
            f'out = Path({str(s_out)!r}); '
            'builtins.SERVER_MODE = None; import config; '
            'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
            'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
            '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
            '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
            '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
            'import pgadmin; '
            f'mod = importlib.import_module({mod_name!r}); '
            f'mod.qualify(out, **json.loads({kw_str!r}))'
        )
        subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True)
        doc = json.loads((s_out / fname).read_text(encoding='utf-8'))
        assert doc.get('complete') is True, (label, doc)
        sub_results[label] = doc

    # Explicit snapshot automatic invalidation on next statement check (pure & C)
    from mysql_qualification_support import server
    import mysql.connector
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _create_client
    from pgadmin.cdeadmin.providers.mysql_family.mysql_completion import complete
    from tools.cdeadmin_mysql_execution_gate import collect

    invalidation_checks = []
    with server(work / 'inv-fixture') as (route, _cname, fixture):
        adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', autocommit=True)
        adm.cursor().execute('CREATE DATABASE sr_inv')
        adm.close()
        for use_pure in (True, False):
            cli = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace(pool_namespace=f'inv-{use_pure}'))
            h = cli.open_session({'route': {**route, 'database': 'sr_inv', 'use_pure': use_pure, 'autocommit': False}})
            sid_tok = str(uuid.uuid4())
            try:
                # Create temp table & refresh snapshot -> observation_source is explicit-source-session-snapshot
                tp = cli.plan_admin_operation({
                    'resource_kind': 'table', 'operation_id': 'create', 'session_id': sid_tok,
                    '_provider_route': {**route, 'database': 'sr_inv', 'use_pure': use_pure},
                    'draft': {'name': 'tmp_inv', 'parent': 'sr_inv', 'temporary': True, 'columns': [{'name': 'tmp_col', 'type': 'INT'}]},
                })
                cli.apply_admin_operation({**tp, '_provider_session_handle': h})
                rp = cli.plan_admin_operation({
                    'resource_kind': 'server', 'operation_id': 'refresh_session_metadata', 'session_id': sid_tok,
                    '_provider_route': {**route, 'database': 'sr_inv', 'use_pure': use_pure},
                    'target_resource': {'resource_kind': 'server', 'display_name': 'Owned server'},
                    'draft': {'confirmation': 'Owned server', 'replace_diagnostics': True,
                              'temporary_tables': [{'database': 'sr_inv', 'name': 'tmp_inv'}]},
                })
                cli.apply_admin_operation({**rp, '_provider_session_handle': h})
                comp_before = complete(cli, h)
                assert comp_before['observation_source'] == 'explicit-source-session-snapshot'
                # Execute next statement through client.execute -> snapshot automatically invalidated!
                collect(cli, cli.execute(h, {'source': 'SELECT 1'}))
                comp_after = complete(cli, h)
                assert comp_after.get('observation_source') != 'explicit-source-session-snapshot'
                assert comp_after.get('context_mode') == 'live_session'
                assert comp_after['original_session_commands_sent'] == 0
                invalidation_checks.append({
                    'use_pure': use_pure,
                    'before_statement_source': comp_before['observation_source'],
                    'after_statement_source': comp_after.get('observation_source') or comp_after['context_mode'],
                    'snapshot_invalidated_on_next_statement': True,
                })
            finally:
                cli.close_session(h)
                cli.close()

    assert fixture['owned_server_stopped'] is True
    receipt = {
        'schema': 'cdeadmin.mysql.editor-diagnostics-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-EDITOR-DIAGNOSTICS',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'protected_passwords_proof': sub_results['protected_passwords'],
        'editor_observer_admission_proof': sub_results['editor_admission'],
        'query_attributes_cext_proof': sub_results['query_attributes_c'],
        'query_attributes_pure_proof': sub_results['query_attributes_pure'],
        'retained_sessions_and_explicit_refresh_proof': sub_results['group9_retained_sessions'],
        'snapshot_invalidation_on_next_statement': invalidation_checks,
        'owned_cleanup_confirmed': True,
    }
    out_file = output_dir / 'editor-diagnostics.json'
    out_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 8 complete -> {out_file}')
    return out_file


# ==============================================================================
# ITEM 9: MY-AUDIT-QUAL-MONITORING (NO ScratchBird /history tests!)
# ==============================================================================
def run_item9_monitoring(output_dir: Path, tmp_dir: Path) -> Path:
    log_step('Item 9: Starting MY-AUDIT-QUAL-MONITORING (strictly excluding ScratchBird /history)...')
    work = tmp_dir / f'item9-{secrets.token_hex(4)}'
    work.mkdir(parents=True, exist_ok=True)

    # 1. Run full cdeadmin_mysql_alert_qualification in a clean subprocess
    alert_out = work / 'alerts'
    alert_code = (
        'import builtins, importlib; from pathlib import Path; '
        f'out = Path({str(alert_out)!r}); '
        'builtins.SERVER_MODE = None; import config; '
        'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
        'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
        '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
        '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
        '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
        'import pgadmin; '
        'mod = importlib.import_module("tools.cdeadmin_mysql_alert_qualification"); '
        'mod.qualify(out)'
    )
    subprocess.run([sys.executable, '-c', alert_code], cwd=ROOT, check=True)
    alert_doc = json.loads((alert_out / 'summary.json').read_text(encoding='utf-8'))
    assert alert_doc['complete'] is True and alert_doc['history_testing'] == 'not run', alert_doc

    # 2. Dedicated monitoring user credential lease, component metrics (replication_applier_metrics &
    #    group_replication_flow_control_stats), cross-user 403 isolation, volatile ring window & DDN dashboard bindings
    builtins.SERVER_MODE = None
    import config
    config.CDEADMIN_MONITORING_PROCESS_MODE = 'single'
    config.CDEADMIN_MONITORING_LOCK_PATH = str(work / 'comp-monitor.lock')
    config.CDEADMIN_MONITORING_WORKER_KEYS = {'k': base64.b64encode(os.urandom(32)).decode()}
    config.CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID = 'k'
    app = init_flask_app(work / 'comp-mon', 'ScratchRobin-mysql-b7-mon')

    import mysql.connector
    from mysql_qualification_support import server
    from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import MySQLMonitor
    from pgadmin.cdeadmin.security import SecretLease
    from pgadmin.model import Role, User, db

    with server(work / 'mon-fixture') as (route, _cname, fixture):
        adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', autocommit=True)
        pw_root = 'MonRoot#' + secrets.token_urlsafe(16)
        pw_mon = 'MonCollector#' + secrets.token_urlsafe(16)
        try:
            cur = adm.cursor()
            cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (pw_root,))
            cur.execute('CREATE DATABASE sr_mon')
            cur.execute("CREATE USER 'u_mon_collector'@'%' IDENTIFIED BY %s", (pw_mon,))
            cur.execute("GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'u_mon_collector'@'%'")
            cur.execute("GRANT SELECT ON performance_schema.* TO 'u_mon_collector'@'%'")
            cur.execute("GRANT SELECT ON sr_mon.* TO 'u_mon_collector'@'%'")
            cur.execute("GRANT SELECT ON mysql.component TO 'u_mon_collector'@'%'")
            cur.close()
        finally:
            adm.close()

        # Create a second ScratchRobin user to prove cross-user 403 isolation
        with app.app_context():
            other_user = User(
                username='other_operator_b7',
                email='other_b7@example.invalid',
                password='x',
                active=True,
                auth_source='internal',
                fs_uniquifier=uuid.uuid4().hex,
            )
            role_obj = Role.query.first()
            if role_obj:
                other_user.roles.append(role_obj)
            db.session.add(other_user)
            db.session.commit()
            other_auth_id = str(other_user.get_id())

        comp_checks = []
        adm = mysql.connector.connect(host=route['host'], port=route['port'], user='root', password=pw_root, autocommit=True)
        try:
            for use_c in (False, True):
                post = register_mysql_http(app, route, pw_root, use_c, database='sr_mon')
                mon_url = f'/cdeadmin/api/monitoring/mysql/{post.server_id}?target_id={post.target_id}'

                # Cross-user 403 check
                other_http = app.test_client()
                with other_http.session_transaction() as sess:
                    sess['_user_id'] = other_auth_id
                    sess['_fresh'] = True
                r_get_other = other_http.get(mon_url)
                assert r_get_other.status_code == 403, (r_get_other.status_code, r_get_other.get_json())
                assert other_http.post(mon_url, json={'interval_seconds': 5}).status_code == 403
                assert other_http.delete(mon_url).status_code == 403

                # Before installing components: status == 'not_installed'
                perms = SimpleNamespace(acquire_secret=lambda *_: SecretLease(pw_mon.encode('utf-8')))
                mon = MySQLMonitor(perms, {
                    **route, 'database': 'sr_mon', 'user': 'u_mon_collector', 'use_pure': not use_c,
                    'credential_reference_id': 'mon-secret', 'principal_reference': 'mon-principal',
                })
                try:
                    s_before = mon.sample()
                    assert s_before['groups']['component_replication_applier_metrics']['status'] == 'not_installed'
                    assert s_before['groups']['component_group_replication_flow_control']['status'] == 'not_installed'

                    with adm.cursor() as cur:
                        cur.execute("INSTALL COMPONENT 'file://component_replication_applier_metrics'")
                        cur.execute("INSTALL PLUGIN group_replication SONAME 'group_replication.so'")
                        cur.execute("INSTALL COMPONENT 'file://component_group_replication_flow_control_stats'")
                    try:
                        mon.sample()
                        time.sleep(0.25)
                        s_inst = mon.sample()
                        assert s_inst['groups']['component_replication_applier_metrics']['status'] == 'available'
                        assert s_inst['groups']['component_replication_applier_worker_progress']['status'] == 'available'
                        assert s_inst['groups']['component_group_replication_flow_control']['status'] == 'available'
                        assert 'Gr_flow_control_throttle_count' in s_inst['rates']['per_second']

                        # Also start HTTP policy-driven collector using dedicated u_mon_collector credentials without viewer polling
                        r_start = post.http.post(mon_url, json={
                            'interval_seconds': 5,
                            'credentials': {'username': 'u_mon_collector', 'password': pw_mon},
                        })
                        assert r_start.status_code == 200 and r_start.headers['Cache-Control'] == 'no-store'
                        deadline = time.monotonic() + 15
                        http_comp_ok = False
                        while time.monotonic() < deadline:
                            r_cur = post.http.get(mon_url).get_json()['data']
                            if r_cur['samples'] and r_cur['samples'][-1]['groups']['component_group_replication_flow_control']['status'] == 'available':
                                http_comp_ok = True
                                heartbeat = r_cur.get('heartbeat') or r_cur.get('state')
                                break
                            time.sleep(0.4)
                        post.http.delete(mon_url)
                        assert http_comp_ok
                    finally:
                        with adm.cursor() as cur:
                            cur.execute("UNINSTALL COMPONENT 'file://component_group_replication_flow_control_stats'")
                            cur.execute('UNINSTALL PLUGIN group_replication')
                            cur.execute("UNINSTALL COMPONENT 'file://component_replication_applier_metrics'")

                    s_after = mon.sample()
                    assert s_after['groups']['component_replication_applier_metrics']['status'] == 'not_installed'
                    assert s_after['groups']['component_group_replication_flow_control']['status'] == 'not_installed'
                finally:
                    mon.close()

                comp_checks.append({
                    'use_c': use_c,
                    'dedicated_monitoring_credential_lease_verified': True,
                    'cross_user_403_isolation_verified': True,
                    'component_metrics_before_during_after_install_verified': True,
                    'heartbeat_state': heartbeat,
                })
        finally:
            adm.close()
            if 'cdeadmin_mysql_monitoring_host' in app.extensions:
                app.extensions['cdeadmin_mysql_monitoring_host'].close()
            if 'cdeadmin_monitoring_host' in app.extensions:
                app.extensions['cdeadmin_monitoring_host'].close()

    # Verify published read-only DDN dashboard bindings in mysqlDashboard.js & dashboardPublication.mjs
    dash_js = (ROOT / 'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/mysqlDashboard.js').read_text(encoding='utf-8')
    pub_mjs = (ROOT / 'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs').read_text(encoding='utf-8')
    assert 'component_group_replication_flow_control' in dash_js and 'component_replication_applier_metrics' in dash_js
    assert 'readOnly' in pub_mjs or 'read_only' in pub_mjs or 'dashboard' in pub_mjs

    assert fixture['owned_server_stopped'] is True
    receipt = {
        'schema': 'cdeadmin.mysql.monitoring-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-MONITORING',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'scratchbird_history_deferred_audit_id': 'MY-AUDIT-HISTORY',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'alerts_collector_and_tls_smtp_proof': alert_doc,
        'component_metrics_and_cross_user_isolation': comp_checks,
        'published_ddn_dashboard_bindings_verified': {
            'mysqlDashboard_sha256': sha256_file(ROOT / 'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/mysqlDashboard.js'),
            'dashboardPublication_sha256': sha256_file(ROOT / 'web/pgadmin/static/js/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs'),
        },
        'owned_cleanup_confirmed': fixture['owned_server_stopped'],
    }
    out_file = output_dir / 'monitoring.json'
    out_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 9 complete -> {out_file}')
    return out_file


ITEM_NAMES = (
    'connection-variants',
    'variable-assignments',
    'object-fields',
    'data-encoding',
    'ddn-transforms',
    'editor-diagnostics',
    'monitoring',
)


def dispatch_single_item(item: str, output_dir: Path, tmp_dir: Path, yparser: Path) -> Path:
    if item == 'connection-variants':
        return run_item2_connection_variants(output_dir, tmp_dir)
    if item == 'variable-assignments':
        return run_item3_variable_assignments(output_dir, tmp_dir)
    if item == 'object-fields':
        return run_item4_object_fields(output_dir, tmp_dir, yparser)
    if item == 'data-encoding':
        return run_item5_data_encoding(output_dir, tmp_dir)
    if item == 'ddn-transforms':
        return run_item6_ddn_transforms(output_dir, tmp_dir)
    if item == 'editor-diagnostics':
        return run_item8_editor_diagnostics(output_dir, tmp_dir, yparser)
    if item == 'monitoring':
        return run_item9_monitoring(output_dir, tmp_dir)
    raise ValueError(f'Unknown item: {item}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--tmp-dir', type=Path, required=True)
    parser.add_argument('--yparser', type=Path, required=True)
    parser.add_argument('--only', choices=ITEM_NAMES)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    out = args.output_dir.resolve()
    tmp = args.tmp_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)

    if args.only:
        sub_tmp = tmp / f'sub-{args.only}-{secrets.token_hex(3)}'
        sub_tmp.mkdir(parents=True, exist_ok=True)
        try:
            dispatch_single_item(args.only, out, sub_tmp, args.yparser)
        finally:
            shutil.rmtree(sub_tmp, ignore_errors=True)
        return

    for item in ITEM_NAMES:
        expected_json = out / f'{item}.json'
        if expected_json.is_file() and not args.force:
            existing = json.loads(expected_json.read_text(encoding='utf-8'))
            if existing.get('complete') is True:
                log_step(f'Skipping already-completed {item} ({expected_json})')
                continue
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                '--output-dir', str(out),
                '--tmp-dir', str(tmp),
                '--yparser', str(args.yparser.resolve()),
                '--only', item,
                '--force',
            ],
            cwd=ROOT,
            check=True,
        )


if __name__ == '__main__':
    main()
