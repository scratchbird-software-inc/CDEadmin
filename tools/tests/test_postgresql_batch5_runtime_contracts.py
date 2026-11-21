"""Live native qualification for PostgreSQL Batch 5:
- PG-AUDIT-COLLECTOR-02: Delegated Kerberos ccache v4 inspection, staging, renewal & expired-ticket refusal
- PG-AUDIT-VERSION-01: Multi-major (PG 16.15, 17.11, 18.6) capability matrix & live execution
- PG-AUDIT-LANGUAGE-01: Target-major AST feature gates, separate authority dimensions, unknown PL grammar & lossless SQL_ASCII
- PG-AUDIT-CAPABILITIES-01: Live bundled extension, FDW, diagnostic (amcheck/pg_stat_statements) & encoding matrix
- PG-AUDIT-POOL-01: Native psycopg_pool adapter, TLS/mTLS, SCRAM, multihost target_session_attrs, isolation modes & generation retirement
"""
from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

import psycopg
from psycopg import sql
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

from pgadmin.cdeadmin.endpoints.capability_sets import (  # noqa: E402
    CONNECTION_CAPABILITY_SETS,
    POSTGRESQL_NATIVE,
    POSTGRESQL_WIRE,
)
from pgadmin.cdeadmin.providers.postgresql.connection_pool import (  # noqa: E402
    PostgreSQLConnectionPoolRegistry,
    PostgreSQLPoolError,
)
from pgadmin.cdeadmin.providers.postgresql.kerberos_delegation import (  # noqa: E402
    KerberosDelegationError,
    build_mit_ccache_v4,
    inspect_ccache,
    renew_ccache,
    stage_isolated_ccache,
)
from pgadmin.cdeadmin.providers.postgresql.language import analyze  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.monitoring import (  # noqa: E402
    PostgreSQLMonitor,
    PostgreSQLMonitoringError,
    io_source,
)
from pgadmin.cdeadmin.providers.postgresql.runtime_capabilities import (  # noqa: E402
    fetch_sql_ascii_rows_lossless,
    inspect_runtime_capabilities,
)
from pgadmin.cdeadmin.providers.postgresql.support_policy import (  # noqa: E402
    effective_capabilities_for_version,
)
from pgadmin.cdeadmin.workspace.postgresql_monitoring_host import (  # noqa: E402
    PostgreSQLMonitoringHost,
)

PG18_BIN = Path('/usr/lib/postgresql/18/bin')
PG17_BIN = Path('/usr/lib/postgresql/17/bin')
PG16_BIN = Path('/usr/lib/postgresql/16/bin')
USER = __import__('getpass').getuser()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_cluster(bin_dir: Path, base: Path, label: str, extra_conf: str = '', hba_text: str | None = None):
    datadir = base / label
    sock_dir = Path(f'/tmp/sr-b5-{uuid.uuid4().hex[:8]}')
    sock_dir.mkdir(mode=0o700, exist_ok=True)
    port = _free_port()
    subprocess.run(
        [
            str(bin_dir / 'initdb'),
            '-D', str(datadir),
            '-U', USER,
            '-A', 'trust',
            '--encoding=UTF8',
            '--locale=C',
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    conf = datadir / 'postgresql.conf'
    conf.write_text(
        conf.read_text(encoding='utf8')
        + f"\nlisten_addresses = '127.0.0.1'\n"
        + f'port = {port}\n'
        + f"unix_socket_directories = '{sock_dir}'\n"
        + extra_conf
        + '\n',
        encoding='utf8',
    )
    if hba_text is not None:
        (datadir / 'pg_hba.conf').write_text(hba_text, encoding='utf8')
    subprocess.run(
        [
            str(bin_dir / 'pg_ctl'),
            '-D', str(datadir),
            '-l', str(base / f'{label}.log'),
            '-w', '-t', '30',
            'start',
        ],
        check=True,
        capture_output=True,
        timeout=35,
    )
    return datadir, port, sock_dir, bin_dir


def _stop_cluster(bin_dir: Path, datadir: Path, sock_dir: Path | None) -> None:
    if datadir.exists() and (datadir / 'postmaster.pid').exists():
        subprocess.run(
            [str(bin_dir / 'pg_ctl'), '-D', str(datadir), '-m', 'immediate', '-w', 'stop'],
            check=False,
            capture_output=True,
            timeout=20,
        )
    if sock_dir and sock_dir.exists():
        shutil.rmtree(sock_dir, ignore_errors=True)


def test_kerberos_delegated_collector_ccache_staging_renewal_and_expiry_refusal(tmp_path):
    """Qualifies PG-AUDIT-COLLECTOR-02."""
    now = int(time.time())
    cc_file = tmp_path / 'krb5cc_valid'
    raw = build_mit_ccache_v4(
        'collector_svc@EXAMPLE.COM',
        'krbtgt/EXAMPLE.COM@EXAMPLE.COM',
        authtime=now - 60,
        starttime=now - 60,
        endtime=now + 30,
        renew_till=now + 3600,
        renewable_flag=True,
    )
    cc_file.write_bytes(raw)
    os.chmod(cc_file, 0o644)
    # Insecure permissions must fail closed
    with pytest.raises(KerberosDelegationError, match='0600'):
        inspect_ccache(cc_file)

    os.chmod(cc_file, 0o600)
    inspected = inspect_ccache(cc_file, now=now)
    assert inspected['default_principal'] == 'collector_svc@EXAMPLE.COM'
    assert inspected['expired'] is False
    assert inspected['renewable'] is True

    staged = stage_isolated_ccache(cc_file, tmp_path / 'staging', now=now)
    assert staged['password_fallback_allowed'] is False
    assert (Path(staged['ccache_path']).stat().st_mode & 0o077) == 0

    # Expired ticket refuses staging & connection with zero password fallback!
    exp_file = tmp_path / 'krb5cc_expired'
    exp_file.write_bytes(
        build_mit_ccache_v4(
            'collector_svc@EXAMPLE.COM',
            'krbtgt/EXAMPLE.COM@EXAMPLE.COM',
            authtime=now - 7200,
            starttime=now - 7200,
            endtime=now - 10,
            renew_till=0,
        )
    )
    os.chmod(exp_file, 0o600)
    with pytest.raises(KerberosDelegationError, match='expired'):
        stage_isolated_ccache(exp_file, tmp_path / 'staging', now=now)

    # Renewal via kinit helper updates ccache expiry cleanly
    fake_kinit = tmp_path / 'fake_kinit.sh'
    renewed_bytes = build_mit_ccache_v4(
        'collector_svc@EXAMPLE.COM',
        'krbtgt/EXAMPLE.COM@EXAMPLE.COM',
        authtime=now,
        starttime=now,
        endtime=now + 1800,
        renew_till=now + 3600,
        renewable_flag=True,
    )
    renewed_source = tmp_path / 'renewed_payload.bin'
    renewed_source.write_bytes(renewed_bytes)
    fake_kinit.write_text(
        '#!/usr/bin/env bash\n'
        'set -euo pipefail\n'
        '# Extract -c FILE:<path>\n'
        'for ((i=1; i<=$#; i++)); do\n'
        '  if [[ "${!i}" == "-c" ]]; then\n'
        '    j=$((i+1)); target="${!j#FILE:}"; cp "' + str(renewed_source) + '" "$target"; chmod 0600 "$target"\n'
        '  fi\n'
        'done\n',
        encoding='utf8',
    )
    os.chmod(fake_kinit, 0o700)
    renewed_info = renew_ccache(staged['ccache_path'], kinit_binary=str(fake_kinit))
    assert renewed_info['renewed'] is True
    assert renewed_info['expires_at'] == now + 1800

    # Verify PostgreSQLMonitor._open uses KRB5CCNAME + require_auth='gss' and NEVER sends a password!
    captured_calls = []

    def fake_connect(**kwargs):
        captured_calls.append({**kwargs, 'env_krb5ccname': os.environ.get('KRB5CCNAME')})
        return SimpleNamespace(info=SimpleNamespace(server_version=180006))

    mon = PostgreSQLMonitor(
        permissions=None,
        route={
            'host': 'db.example.internal',
            'port': 5432,
            'user': 'collector_svc',
            'database': 'postgres',
            'principal_reference': 'user:1',
            'credential_reference_id': 'kerberos-delegated-ccache',
            'connection_params': {'gssencmode': 'prefer'},
            'kerberos_delegation': {'ccache_path': staged['ccache_path'], 'renew_before_seconds': 5},
        },
        connect=fake_connect,
    )
    mon._open()
    assert len(captured_calls) == 1
    assert 'password' not in captured_calls[0]
    assert captured_calls[0]['require_auth'] == 'gss'
    assert captured_calls[0]['env_krb5ccname'] == f"FILE:{staged['ccache_path']}"

    # Expired non-renewable ccache in monitor fails closed with PostgreSQLMonitoringError
    mon_exp = PostgreSQLMonitor(
        permissions=None,
        route={
            'host': 'db.example.internal',
            'port': 5432,
            'user': 'collector_svc',
            'database': 'postgres',
            'principal_reference': 'user:1',
            'credential_reference_id': 'kerberos-delegated-ccache',
            'connection_params': {},
            'kerberos_delegation': {'ccache_path': str(exp_file), 'renew_before_seconds': 0},
        },
        connect=fake_connect,
    )
    with pytest.raises(PostgreSQLMonitoringError, match='expired'):
        mon_exp._open()


def test_multi_major_version_matrix_and_language_semantics_live(tmp_path):
    """Qualifies PG-AUDIT-VERSION-01 and PG-AUDIT-LANGUAGE-01 across live PG 16.15, 17.11 & 18.6."""
    caps_json = json.loads(
        (ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/postgresql/capabilities.json').read_text(encoding='utf8')
    )
    assert caps_json['version_range']['minimum'] == '15.0'
    assert {'16', '17', '18'} <= set(caps_json['version_range']['tested'])

    audit_day = date(2026, 11, 21)
    assert effective_capabilities_for_version(140025, today=audit_day)['admitted'] is False
    c15 = effective_capabilities_for_version(150020, today=audit_day)
    c16 = effective_capabilities_for_version(160015, today=audit_day)
    c17 = effective_capabilities_for_version(170011, today=audit_day)
    c18 = effective_capabilities_for_version(180006, today=audit_day)
    assert c15['admitted'] and c15['features']['merge_statement'] and not c15['features']['pg_stat_io']
    assert c16['admitted'] and c16['features']['pg_stat_io'] and not c16['features']['incremental_physical_backup']
    assert c17['admitted'] and c17['features']['merge_returning'] and not c17['features']['virtual_generated_columns']
    assert c18['admitted'] and c18['features']['virtual_generated_columns'] and c18['features']['not_enforced_constraints']

    # Language target-major AST feature gates & explicit authority separation
    virt_sql = 'CREATE TABLE t (x int, y int GENERATED ALWAYS AS (x + 1) VIRTUAL)'
    r17 = analyze(virt_sql, standard_strings='on', target_server_version=170011)
    r18 = analyze(virt_sql, standard_strings='on', target_server_version=180006)
    assert r17['grammar_valid'] is False and r17['target_version_compatible'] is False
    assert r17['diagnostics'][0]['code'] == 'VERSION_FEATURE_UNSUPPORTED'
    assert r18['grammar_valid'] is True and r18['target_version_compatible'] is True
    assert r18['catalog_binding_status'] == 'not_evaluated'
    assert r18['privilege_evaluation'] == 'not_evaluated'
    assert r18['execution_verified'] is False

    merge_ret = 'MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN DELETE RETURNING t.id'
    assert analyze(merge_ret, standard_strings='on', target_server_version=160015)['target_version_compatible'] is False
    assert analyze(merge_ret, standard_strings='on', target_server_version=170011)['target_version_compatible'] is True

    for pl_lang in ('plpython3u', 'plperl', 'pltcl'):
        pl_res = analyze(f'CREATE FUNCTION f() RETURNS int LANGUAGE {pl_lang} AS $$return 1$$', standard_strings='on')
        assert pl_res['grammar_valid'] is None
        assert pl_res['grammar_status'] == 'unknown'

    # Live multi-major execution across PG 16.15, PG 17.11, and PG 18.6!
    clusters = []
    try:
        for bdir, lbl in ((PG16_BIN, 'pg16'), (PG17_BIN, 'pg17'), (PG18_BIN, 'pg18')):
            if (bdir / 'initdb').is_file():
                clusters.append(_start_cluster(bdir, tmp_path, lbl))
        assert len(clusters) == 3, 'Expected all three PG 16, 17, and 18 local runtimes'

        observed_majors = []
        for _ddir, port, _sdir, _bdir in clusters:
            dsn = f'host=127.0.0.1 port={port} user={USER} dbname=postgres'
            with psycopg.connect(dsn, autocommit=True) as conn:
                ver_num = conn.info.server_version
                eff = effective_capabilities_for_version(ver_num, today=audit_day)
                assert eff['admitted'] is True
                observed_majors.append(eff['major'])
                # Verify version-specific pg_stat_io query executes cleanly on every major!
                io_q = io_source(ver_num)
                assert io_q is not None
                rows = conn.execute(io_q).fetchall()
                assert len(rows) >= 1
        assert observed_majors == [16, 17, 18]
    finally:
        for ddir, _port, sdir, bdir in clusters:
            _stop_cluster(bdir, ddir, sdir)


def test_runtime_capabilities_bundled_extensions_sql_ascii_and_pool_tls_variants_live(tmp_path):
    """Qualifies PG-AUDIT-CAPABILITIES-01, SQL_ASCII lossless bytes, and PG-AUDIT-POOL-01 on live PG 18.6."""
    # 1. Verify postgresql-native-v1 retains all 14 categories & every feature without borrowing distributed tests
    assert 'postgresql-native-v1' in CONNECTION_CAPABILITY_SETS
    assert set(POSTGRESQL_NATIVE) == set(POSTGRESQL_WIRE)
    for cat, spec in POSTGRESQL_NATIVE.items():
        assert spec['features'] == POSTGRESQL_WIRE[cat]['features'], cat
        assert all('distributed_providers' not in ev for ev in spec['evidence']), cat

    # 2. Generate ephemeral CA, server cert/key, and client cert/key via openssl for live TLS/mTLS verification!
    tls_dir = tmp_path / 'tls'
    tls_dir.mkdir(mode=0o700)
    subprocess.run(
        ['openssl', 'req', '-new', '-x509', '-days', '1', '-nodes', '-out', str(tls_dir / 'ca.crt'),
         '-keyout', str(tls_dir / 'ca.key'), '-subj', '/CN=ScratchRobinTestCA'],
        check=True, capture_output=True,
    )
    for role_cn, prefix in (('127.0.0.1', 'server'), ('sr_mtls_user', 'client')):
        subprocess.run(
            ['openssl', 'req', '-new', '-nodes', '-out', str(tls_dir / f'{prefix}.csr'),
             '-keyout', str(tls_dir / f'{prefix}.key'), '-subj', f'/CN={role_cn}'],
            check=True, capture_output=True,
        )
        ext_file = tls_dir / f'{prefix}.ext'
        if prefix == 'server':
            ext_file.write_text('subjectAltName = IP:127.0.0.1,DNS:localhost\n', encoding='utf8')
            ext_args = ['-extfile', str(ext_file)]
        else:
            ext_args = []
        subprocess.run(
            ['openssl', 'x509', '-req', '-in', str(tls_dir / f'{prefix}.csr'),
             '-CA', str(tls_dir / 'ca.crt'), '-CAkey', str(tls_dir / 'ca.key'),
             '-CAcreateserial', '-days', '1', '-out', str(tls_dir / f'{prefix}.crt'), *ext_args],
            check=True, capture_output=True,
        )
        os.chmod(tls_dir / f'{prefix}.key', 0o600)

    extra_conf = (
        "ssl = on\n"
        f"ssl_cert_file = '{tls_dir / 'server.crt'}'\n"
        f"ssl_key_file = '{tls_dir / 'server.key'}'\n"
        f"ssl_ca_file = '{tls_dir / 'ca.crt'}'\n"
        "shared_preload_libraries = 'pg_stat_statements'\n"
        "password_encryption = 'scram-sha-256'\n"
    )
    hba = (
        f'hostssl all sr_mtls_user 127.0.0.1/32 cert\n'
        f'hostssl all sr_scram_user 127.0.0.1/32 scram-sha-256\n'
        f'host all {USER} 127.0.0.1/32 trust\n'
        f'local all all trust\n'
    )
    ddir, port, sdir, bdir = _start_cluster(PG18_BIN, tmp_path, 'pg18_caps_pool', extra_conf=extra_conf, hba_text=hba)
    pool_reg = PostgreSQLConnectionPoolRegistry()
    try:
        dsn = f'host=127.0.0.1 port={port} user={USER} dbname=postgres'
        with psycopg.connect(dsn, autocommit=True) as conn:
            # Install bundled extensions & verify runtime capabilities matrix!
            extensions_to_install = [
                'btree_gist', 'amcheck', 'pg_stat_statements', 'postgres_fdw',
                'hstore', 'citext', 'ltree', 'pgcrypto', 'uuid-ossp',
            ]
            for ext in extensions_to_install:
                conn.execute(sql.SQL('CREATE EXTENSION IF NOT EXISTS {}').format(sql.Identifier(ext)))

            conn.execute('CREATE TABLE public.cap_probe (id int primary key, payload text)')
            conn.execute("INSERT INTO public.cap_probe VALUES (1, 'verified')")
            # Run amcheck bt_index_check on live B-tree index!
            conn.execute("SELECT bt_index_check('public.cap_probe_pkey')")

            caps = inspect_runtime_capabilities(conn)
            inst_names = {e['name'] for e in caps['installed_extensions']}
            assert set(extensions_to_install) <= inst_names
            assert caps['diagnostics']['pg_stat_statements_installed'] is True
            assert caps['diagnostics']['pg_stat_statements_preloaded'] is True
            assert caps['diagnostics']['amcheck_installed'] is True
            assert caps['diagnostics']['postgres_fdw_installed'] is True
            assert any(f['name'] == 'postgres_fdw' and f['has_handler'] for f in caps['foreign_data_wrappers'])

            # Create SQL_ASCII & LATIN1 databases and verify lossless SQL_ASCII non-UTF8 byte round-trip!
            conn.execute("CREATE DATABASE db_latin1 TEMPLATE template0 ENCODING 'LATIN1' LC_COLLATE 'C' LC_CTYPE 'C'")
            conn.execute("CREATE DATABASE db_sql_ascii TEMPLATE template0 ENCODING 'SQL_ASCII' LC_COLLATE 'C' LC_CTYPE 'C'")

            # Create SCRAM and mTLS users
            conn.execute("CREATE ROLE sr_scram_user LOGIN PASSWORD 'Scram#Secret!2026'")
            conn.execute('CREATE ROLE sr_mtls_user LOGIN')

        # Test SQL_ASCII non-UTF8 raw byte roundtrip without replacement corruption!
        raw_non_utf8 = b'\x80\xff\xfeSQL_ASCII_RAW\xc3\x28'
        ascii_dsn = f'host=127.0.0.1 port={port} user={USER} dbname=db_sql_ascii'
        with psycopg.connect(ascii_dsn, autocommit=True) as aconn:
            aconn.execute("SET client_encoding = 'SQL_ASCII'")
            aconn.execute('CREATE TABLE public.raw_ascii (id int primary key, raw_text text)')
            aconn.execute(
                "INSERT INTO public.raw_ascii VALUES (1, convert_from(%s::bytea, 'SQL_ASCII'))",
                (raw_non_utf8,),
            )
            lossless = fetch_sql_ascii_rows_lossless(aconn, 'public', 'raw_ascii')
            assert len(lossless) == 1
            cell = lossless[0][1]
            assert cell['utf8_valid'] is False
            assert cell['raw_hex'] == raw_non_utf8.hex()

        # Test SCRAM-SHA-256 + TLS verify-full + channel_binding=require!
        with psycopg.connect(
            host='127.0.0.1',
            port=port,
            user='sr_scram_user',
            password='Scram#Secret!2026',
            dbname='postgres',
            sslmode='verify-full',
            sslrootcert=str(tls_dir / 'ca.crt'),
            channel_binding='require',
            require_auth='scram-sha-256',
        ) as sconn:
            assert sconn.execute('SELECT current_user').fetchone()[0] == 'sr_scram_user'

        # Test mutual-TLS client-certificate authentication (no password)!
        with psycopg.connect(
            host='127.0.0.1',
            port=port,
            user='sr_mtls_user',
            dbname='postgres',
            sslmode='verify-full',
            sslrootcert=str(tls_dir / 'ca.crt'),
            sslcert=str(tls_dir / 'client.crt'),
            sslkey=str(tls_dir / 'client.key'),
        ) as mconn:
            assert mconn.execute('SELECT current_user').fetchone()[0] == 'sr_mtls_user'

        # Test multihost failover + target_session_attrs=read-write (dead port first, live primary second)!
        dead_port = _free_port()
        with psycopg.connect(
            f'host=127.0.0.1,127.0.0.1 port={dead_port},{port} user={USER} dbname=postgres '
            'target_session_attrs=read-write connect_timeout=3'
        ) as mh_conn:
            assert mh_conn.execute('SELECT pg_is_in_recovery()').fetchone()[0] is False

        # Test 4 isolation levels + READ ONLY + DEFERRABLE!
        with psycopg.connect(dsn, autocommit=True) as iconn:
            for iso in ('READ UNCOMMITTED', 'READ COMMITTED', 'REPEATABLE READ', 'SERIALIZABLE'):
                iconn.execute(f'BEGIN ISOLATION LEVEL {iso} READ ONLY' + (' DEFERRABLE' if iso == 'SERIALIZABLE' else ''))
                observed_iso = iconn.execute('SHOW transaction_isolation').fetchone()[0]
                assert observed_iso == iso.lower()
                iconn.execute('ROLLBACK')

        # Test native psycopg_pool: checkout, validation after backend kill, timeout refusal, and generation retirement!
        pool_params = {'host': '127.0.0.1', 'port': port, 'user': USER, 'dbname': 'postgres', 'sslmode': 'disable'}
        policy = {
            'enabled': True,
            'min_size': 1,
            'max_size': 1,
            'acquisition_timeout': 0.4,
            'queue_limit': 2,
            'lifetime': 120.0,
            'idle_timeout': 60.0,
            'checkout_validation': True,
            'background_reconnect_window': 5.0,
        }
        with pool_reg.connection('ep-pg18', 'gen-1', pool_params, policy) as pconn1:
            pid1 = pconn1.info.backend_pid
            # Exhaust max_size=1 -> second checkout times out cleanly with PostgreSQLPoolError!
            with pytest.raises(PostgreSQLPoolError, match='timed out'):
                with pool_reg.connection('ep-pg18', 'gen-1', pool_params, policy, timeout=0.25):
                    pass

        # Terminate idle pooled backend on server -> checkout_validation transparently replaces broken socket!
        with psycopg.connect(dsn, autocommit=True) as killer:
            killer.execute('SELECT pg_catalog.pg_terminate_backend(%s)', (pid1,))
        time.sleep(0.1)
        with pool_reg.connection('ep-pg18', 'gen-1', pool_params, policy) as pconn2:
            assert pconn2.execute('SELECT 1').fetchone()[0] == 1
            assert pconn2.info.backend_pid != pid1

        # Rotating to generation 'gen-2' retires 'gen-1' immediately!
        with pool_reg.connection('ep-pg18', 'gen-2', pool_params, policy) as pconn3:
            assert pconn3.execute('SELECT 1').fetchone()[0] == 1
        st = pool_reg.stats('ep-pg18')
        assert [p['generation'] for p in st['active_pools']] == ['gen-2']
        assert any(r['generation'] == 'gen-1' and r['closed'] is True for r in st['retired_generations'])
    finally:
        pool_reg.close_all()
        _stop_cluster(bdir, ddir, sdir)
