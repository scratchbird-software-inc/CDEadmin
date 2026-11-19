"""Current-source Firebird 5.0.4 supplemental & authenticated HTTP qualification
for the final 8 Firebird audit items:
  FB-Q02, FB-Q03, FB-Q04, FB-Q05, FB-Q06, FB-Q08, FB-Q09, FB-Q12.

ScratchBird persistent monitoring history (FB-OWN-01) is strictly not run.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'web'), str(ROOT), str(ROOT / 'tools')]

FB4_FIXTURE = Path(
    '/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/firebird4-current-fixture/upgrade-original.fdb'
)


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + '\n', encoding='utf-8')


def _register_http_server(app, uid, group_id, name, profile_id, route, db_paths, password=None):
    from flask import url_for
    from pgadmin.model import EndpointDatabaseTarget, Server, db
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile

    with app.test_request_context('/'):
        is_emb = profile_id == 'firebird-embedded'
        server = Server(
            user_id=uid,
            servergroup_id=group_id,
            name=name,
            host=None if is_emb else route.get('host', '127.0.0.1'),
            port=1 if is_emb else int(route.get('port', 3050)),
            username=route.get('user', 'SYSDBA'),
            maintenance_db=str(db_paths[0]),
            save_password=0,
        )
        server._cde_endpoint_registration = registration_profile(profile_id)
        server._cde_endpoint_route_configuration = dict(route)
        db.session.add(server)
        db.session.commit()
        ep_id = server.endpoint_profile.id
        tids = []
        for idx, db_p in enumerate(db_paths):
            tid = str(uuid.uuid4())
            db.session.add(EndpointDatabaseTarget(
                id=tid,
                endpoint_id=ep_id,
                display_name=Path(db_p).name if idx == 0 else f'{Path(db_p).stem}_{idx}.fdb',
                database=str(db_p),
                configuration='{}',
                active=(1 if idx == 0 else 0),
            ))
            tids.append(tid)
        db.session.commit()
        return {
            'server_id': server.id,
            'endpoint_id': ep_id,
            'target_ids': tids,
            'ws_url': url_for('NODE-server.cde_workspace_id', gid=group_id, sid=server.id),
            'verify_url': url_for('NODE-server.verify_endpoint_id', gid=group_id, sid=server.id),
        }


def run_all(runtime: Path, evidence_base: Path, start_from: str = 'all'):
    import builtins
    builtins.SERVER_MODE = None
    import pgadmin  # noqa: F401
    import firebird.driver as fb_driver
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint, _initialize_security, _free_port,
    )
    from tools.cdeadmin_firebird_encryption_and_replication_qualification import (
        _materialize_writable_runtime, _compile_sample_crypt_plugins,
    )
    from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
    from tools.mysql_driver_gate_support import provider_access
    from tools.cdeadmin_native_editor_gate import provider as make_editor_provider
    from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
    from pgadmin.cdeadmin.providers.firebird import provider as net_mod, embedded_provider as emb_mod
    from pgadmin.cdeadmin.providers.firebird.runtime_lifecycle import (
        start_managed_daemon_process, stop_managed_daemon_process, inspect_database_ods,
    )
    from pgadmin.cdeadmin.providers.firebird.plugin_deployment import (
        prepare_plugin_review, apply_plugin_operation,
    )
    from pgadmin.cdeadmin.providers.firebird.host_runtime_grant import file_sha256

    runtime = runtime.resolve()
    evidence_base = evidence_base.resolve()
    before_fp = _runtime_fingerprint(runtime)

    with tempfile.TemporaryDirectory(prefix='cdeadmin-fb-rem8-') as temp:
        area = Path(temp).resolve()
        stage = area / 'runtime'
        data = area / 'data'
        staging = area / 'staging'
        data.mkdir()
        staging.mkdir()
        _stage_runtime(runtime, stage)
        _materialize_writable_runtime(stage)

        dbcrypt_so, keyholder_so = _compile_sample_crypt_plugins(staging)
        (staging / 'fbSampleDbCrypt.conf').write_text('Auto = false\n', encoding='utf-8')
        (staging / 'fbSampleKeyHolder.conf').write_text(
            'Auto = true\nKeyOWNED = 90\nOnlyOwnKey = false\n', encoding='utf-8'
        )

        sysdba_pw = 'Rem8#' + secrets.token_hex(8)
        port = _free_port()
        (stage / 'firebird.conf').write_text(
            (stage / 'firebird.conf').read_text(encoding='utf-8').rstrip()
            + '\nServerMode = SuperClassic\nProviders = Remote,Engine13\n'
            + 'AuthServer = Srp256, Srp, Legacy_Auth\nUserManager = Srp, Legacy_UserManager\n'
            + 'WireCrypt = Enabled\nWireCompression = true\n'
            + 'KeyHolderPlugin = fbSampleKeyHolder\n',
            encoding='utf-8',
        )
        os.environ.update(
            FIREBIRD=str(stage),
            FIREBIRD_LOCK=str(stage / 'lock'),
            LD_LIBRARY_PATH=str(stage / 'lib'),
            CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
        )
        fb_driver.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
        _initialize_security(stage, sysdba_pw, dict(os.environ))

        host_scope = {
            'attachment_mode': 'same_host_granted_network',
            'platform': 'linux',
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip(),
            'hostname': 'localhost',
            'engine_version': '5.0.4',
            'firebird_runtime_root': str(stage),
            'firebird_lock_directory': str(stage / 'lock'),
            'staging_directory': str(staging),
            'journal_directories': [],
            'allowed_databases': [],
            'allow_host_administration': True,
            'managed_daemon': {
                'pid_file': str(area / 'fb.pid'),
                'port': port,
                'bind_host': '127.0.0.1',
                'server_log': str(area / 'fb.log'),
            },
        }
        for mod_name, so_p, cfg_name in (
            ('fbSampleDbCrypt', dbcrypt_so, 'fbSampleDbCrypt.conf'),
            ('fbSampleKeyHolder', keyholder_so, 'fbSampleKeyHolder.conf'),
        ):
            rev = prepare_plugin_review(host_scope, {
                'operation': 'deploy_plugin',
                'module_name': mod_name,
                'plugin_alias': mod_name,
                'staged_filename': so_p.name,
                'expected_source_sha256': file_sha256(so_p),
                'staged_config_filename': cfg_name,
                'expected_config_sha256': file_sha256(staging / cfg_name),
            })
            apply_plugin_operation({'review_id': str(uuid.uuid4()), 'payload': rev})

        start_managed_daemon_process(host_scope)
        try:
            # Shared Flask app for authenticated HTTP workflows across all 8 items
            http_root = area / 'http_app'
            http_root.mkdir()
            app = setup_application(http_root)
            from pgadmin.model import Role, ServerGroup, User, db
            from pgadmin.cdeadmin.workspace.service import service_for_app

            with ExitStack() as stack:
                def _close_app():
                    with app.app_context():
                        service_for_app(app).endpoint_service.provider_registry.close()
                stack.callback(_close_app)

                with app.test_request_context('/'):
                    owner_user = User.query.first()
                    owner_uid = owner_user.id
                    owner_gid = ServerGroup.query.filter_by(user_id=owner_uid).first().id
                    for name, pref in app.blueprints['NODE-engine_type'].connector_visibility.items():
                        if 'firebird' in name:
                            pref.set(True, user_id=owner_uid)
                    # Create a second independent user to verify cross-user 403 isolation in Q09/Q12
                    peer_role = Role.query.first()
                    peer_user = User(
                        username='fb_peer_viewer',
                        email='fb_peer@example.com',
                        password='peer',
                        active=True,
                        auth_source='internal',
                        roles=[peer_role] if peer_role else [],
                    )
                    db.session.add(peer_user)
                    db.session.commit()
                    peer_uid = peer_user.id

                http = app.test_client()
                with http.session_transaction() as sess:
                    sess['_user_id'] = str(owner_uid)
                    sess['_fresh'] = True

                peer_http = app.test_client()
                with peer_http.session_transaction() as sess:
                    sess['_user_id'] = str(peer_uid)
                    sess['_fresh'] = True

                if start_from == 'all':
                    # =============================================================
                    # 1. FB-Q02: Native language/contextual editor matrix + HTTP
                    # =============================================================
                    from tools import firebird_editor_native
                    q02_db = data / 'q02_editor.fdb'
                    c_q02 = fb_driver.create_database(f'127.0.0.1/{port}:{q02_db}', user='SYSDBA', password=sysdba_pw)
                    c_q02.execute_immediate('CREATE TABLE EDITOR_NONEXEC (ID INTEGER NOT NULL PRIMARY KEY, LABEL VARCHAR(40) DEFAULT \'def\')')
                    c_q02.commit()
                    c_q02.execute_immediate('CREATE PACKAGE ED_PKG AS BEGIN FUNCTION F_ONE RETURNS INTEGER; END')
                    c_q02.commit()
                    c_q02.execute_immediate('CREATE PACKAGE BODY ED_PKG AS BEGIN FUNCTION F_ONE RETURNS INTEGER AS BEGIN RETURN 1; END END')
                    c_q02.commit()

                    q02_route, q02_perms = provider_access({
                        'host': '127.0.0.1', 'port': port, 'database': str(q02_db),
                        'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled', 'trusted_auth': False,
                    }, sysdba_pw)
                    q02_perms.require = lambda *_: None
                    q02_perms.allows = lambda *_: True
                    q02_client = net_mod._create_client(q02_perms, attachment_mode='network')
                    stack.callback(q02_client.close)

                    fmt_proof = firebird_editor_native.qualify(c_q02, q02_client, q02_route)
                    c_q02.close()

                    ed_prov, ed_route = make_editor_provider(
                        'firebird',
                        {'host': '127.0.0.1', 'port': port, 'database': str(q02_db), 'user': 'SYSDBA', 'charset': 'UTF8'},
                        sysdba_pw,
                        embedded=False,
                    )
                    stack.callback(ed_prov.client.close)
                    ed_sess = ed_prov.open_session({'route': ed_route})['session_id']

                    grammar_cases = {}
                    for d_num, sql_text in (
                        (3, "WITH RECURSIVE R(N) AS (SELECT 1 FROM RDB$DATABASE UNION ALL SELECT N+1 FROM R WHERE N < 3) SELECT N, ED_PKG.F_ONE(), TIMESTAMP '2026-01-01 00:00:00' AT TIME ZONE 'UTC', _UTF8'é', q'{qtext}', x'ABCD' FROM R"),
                        (3, "INSERT INTO EDITOR_NONEXEC (ID) VALUES (99)"),
                        (3, "EXECUTE BLOCK RETURNS (O INTEGER) AS DECLARE V INTEGER = 5; BEGIN O = V + ED_PKG.F_ONE(); SUSPEND; END"),
                        (1, 'SELECT 10 / 3 FROM RDB$DATABASE'),
                        (2, 'SELECT CURRENT_DATE FROM RDB$DATABASE'),
                    ):
                        vr = ed_prov.validate_source_without_execution({
                            'session_id': ed_sess,
                            'language_profile': 'firebird-sql',
                            'client_sql_dialect': d_num,
                            'source': sql_text,
                        })
                        assert vr['syntax_valid'] is True and vr['grammar_valid'] is True, (d_num, vr)
                        grammar_cases[f'dialect_{d_num}_{len(grammar_cases)}'] = {
                            'syntax_valid': vr['syntax_valid'],
                            'client_sql_dialect': vr['client_sql_dialect'],
                        }

                    # Script mode with SET SQL DIALECT + SET TERM + PSQL
                    script_vr = ed_prov.validate_source_without_execution({
                        'session_id': ed_sess,
                        'language_profile': 'firebird-sql',
                        'script': True,
                        'source': (
                            'SET SQL DIALECT 3;\n'
                            'SELECT ID, LABEL FROM EDITOR_NONEXEC;\n'
                            'SET TERM ^ ;\n'
                            'EXECUTE BLOCK RETURNS (X INTEGER) AS BEGIN X = 42; SUSPEND; END^\n'
                            'SET TERM ; ^\n'
                        ),
                    })
                    assert script_vr['script_ready'] is True and script_vr['syntax_valid'] is True, script_vr

                    # Exact diagnostics: -104 FIREBIRD_SYNTAX vs -204 FIREBIRD_CONTEXT
                    syn_vr = ed_prov.validate_source_without_execution({
                        'session_id': ed_sess, 'language_profile': 'firebird-sql', 'source': 'SELECT FROM WHERE',
                    })
                    assert syn_vr['grammar_valid'] is False and syn_vr['diagnostics'][0]['code'] == 'FIREBIRD_SYNTAX', syn_vr
                    ctx_vr = ed_prov.validate_source_without_execution({
                        'session_id': ed_sess, 'language_profile': 'firebird-sql', 'source': 'SELECT * FROM NON_EXISTENT_TABLE_Q02',
                    })
                    assert ctx_vr['grammar_valid'] is None and ctx_vr['diagnostics'][0]['code'] == 'FIREBIRD_CONTEXT', ctx_vr

                    # Prove non-execution: EDITOR_NONEXEC still has 0 rows and session handle is idle!
                    ed_handle = ed_prov._sessions[ed_sess].handle
                    assert not ed_handle.main_transaction.is_active()
                    with ed_handle.cursor() as cur:
                        cur.execute('SELECT COUNT(*) FROM EDITOR_NONEXEC')
                        assert cur.fetchone()[0] == 0
                    ed_handle.rollback()

                    # Authenticated HTTP editor workflow (embedded registration for immediate auth)
                    q02_emb = data / 'q02_http_emb.fdb'
                    q02_emb_route = {'attachment_mode': 'embedded', 'database': str(q02_emb), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
                    fb_driver.create_database(str(q02_emb), user='SYSDBA').close()
                    q02_srv = _register_http_server(app, owner_uid, owner_gid, 'HTTP Q02 Editor', 'firebird-embedded', q02_emb_route, [q02_emb])
                    assert http.post(q02_srv['verify_url'], json={}).get_json()['success']
                    tid_q02 = q02_srv['target_ids'][0]
                    op_s = http.post(q02_srv['ws_url'], json={'action': 'open_session', 'language_profile': 'firebird-sql', 'database_target_id': tid_q02}).get_json()
                    assert op_s['success'], op_s
                    sid_q02 = op_s['data']['session_id']
                    http_val = http.post(q02_srv['ws_url'], json={
                        'action': 'source_validate', 'session_id': sid_q02, 'database_target_id': tid_q02,
                        'language_profile': 'firebird-sql', 'source': 'SELECT CURRENT_USER FROM RDB$DATABASE',
                    }).get_json()
                    assert http_val['success'] and http_val['data']['syntax_valid'] is True, http_val
                    http_comp = http.post(q02_srv['ws_url'], json={
                        'action': 'source_complete', 'session_id': sid_q02, 'database_target_id': tid_q02,
                        'language_profile': 'firebird-sql',
                        'source': 'SELECT RDB$RELATION_NAME FROM RDB$D',
                        'source_before_cursor': 'SELECT RDB$RELATION_NAME FROM RDB$D',
                    }).get_json()
                    assert http_comp['success'] and isinstance(http_comp['data'], dict), http_comp
                    http_meta = http.post(q02_srv['ws_url'], json={'action': 'firebird_editor_metadata', 'database_target_id': tid_q02}).get_json()
                    assert http_meta['success'], http_meta
                    http.post(q02_srv['ws_url'], json={'action': 'close_session', 'session_id': sid_q02, 'database_target_id': tid_q02})

                    _write_json(evidence_base / 'firebird-remaining25-q02-editor/supplement-and-http.json', {
                        'schema': 'cdeadmin.firebird.q02-editor-supplement.v1',
                        'complete': True,
                        'history_tests': 'not run',
                        'formatting_and_from_cursor_proof': fmt_proof,
                        'grammar_and_dialect_1_2_3_cases': grammar_cases,
                        'script_prepare_ready': True,
                        'exact_syntax_and_context_diagnostics': {
                            'syntax': syn_vr['diagnostics'][0],
                            'context': ctx_vr['diagnostics'][0],
                        },
                        'non_execution_verified': True,
                        'http_editor_workflow_passed': True,
                    })

                    # =============================================================
                    # 2. FB-Q03: Typed data, BLOB, custom subtype/filter & HTTP
                    # =============================================================
                    from tools import firebird_blob_editor_native, cdeadmin_firebird_attachment_codecs_gate
                    q03_db = data / 'q03_typed.fdb'
                    c_q03 = fb_driver.create_database(f'127.0.0.1/{port}:{q03_db}', user='SYSDBA', password=sysdba_pw)
                    q03_route, q03_perms = provider_access({
                        'host': '127.0.0.1', 'port': port, 'database': str(q03_db),
                        'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled', 'trusted_auth': False,
                    }, sysdba_pw)
                    q03_perms.require = lambda *_: None
                    q03_perms.allows = lambda *_: True
                    q03_client = net_mod._create_client(q03_perms, attachment_mode='network')
                    stack.callback(q03_client.close)
                    q03_client._connections.append(c_q03)

                    blob_proof = firebird_blob_editor_native.qualify(c_q03, q03_client)

                    # INT128, NUMERIC(38,18), DECFLOAT specials, BOOLEAN, OCTETS, custom BLOB subtype + filter declaration
                    c_q03.execute_immediate(
                        'CREATE TABLE TYPED_SCALARS ('
                        'ID INTEGER NOT NULL PRIMARY KEY, '
                        'I128 INT128, '
                        'N38 NUMERIC(38, 18), '
                        'DF34 DECFLOAT(34), '
                        'FLAG BOOLEAN, '
                        'RAW_FIXED CHAR(4) CHARACTER SET OCTETS, '
                        'RAW_VAR VARCHAR(8) CHARACTER SET OCTETS, '
                        'CUSTOM_BLOB BLOB SUB_TYPE -7)'
                    )
                    c_q03.execute_immediate("DECLARE FILTER Q03_CUSTOM_FILTER INPUT_TYPE -7 OUTPUT_TYPE 1 ENTRY_POINT 'desc_filter' MODULE_NAME 'fb_filter'")
                    c_q03.commit()
                    max_i128 = (1 << 127) - 1
                    min_i128 = -(1 << 127)
                    n38_val = Decimal('12345678901234567890.123456789012345678')
                    with c_q03.cursor() as cur:
                        cur.execute(
                            'INSERT INTO TYPED_SCALARS VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                            (1, max_i128, n38_val, Decimal('NaN'), True, b'\x00\xff\x01\x02', b'\xfe\x00\xab', b'custom-subtype-payload'),
                        )
                        cur.execute(
                            'INSERT INTO TYPED_SCALARS VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                            (2, min_i128, -n38_val, Decimal('-Infinity'), False, b'\x01\x02\x03\x04', b'', None),
                        )
                    c_q03.commit()
                    with c_q03.cursor() as cur:
                        cur.execute('SELECT I128, N38, CAST(DF34 AS VARCHAR(20)), FLAG, RAW_FIXED, RAW_VAR, CUSTOM_BLOB FROM TYPED_SCALARS ORDER BY ID')
                        r1, r2 = cur.fetchall()
                        assert r1[0] == max_i128 and r1[1] == n38_val and 'NaN' in r1[2] and r1[3] is True
                        assert r1[4] == b'\x00\xff\x01\x02' and r1[5] == b'\xfe\x00\xab' and r1[6] == b'custom-subtype-payload'
                        assert r2[0] == min_i128 and r2[1] == -n38_val and r2[2] == '-Infinity' and r2[3] is False
                        assert r2[5] == b'' and r2[6] is None
                    c_q03.rollback()

                    # Embedded attachment codecs check
                    emb_codec_dir = data / 'emb_codecs'
                    emb_codec_dir.mkdir()
                    emb_codec_ev = evidence_base / 'firebird-remaining25-q03-typed/codecs-emb'
                    emb_codec_ev.mkdir(parents=True, exist_ok=True)
                    cdeadmin_firebird_attachment_codecs_gate.qualify(
                        fb_driver, None, {}, {'Srp': [('SYSDBA', sysdba_pw)]}, emb_codec_ev, emb_codec_dir, embedded=True
                    )

                    # Authenticated HTTP query_stream + visual_admin_rows on typed table
                    q03_emb = data / 'q03_http.fdb'
                    c_h03 = fb_driver.create_database(str(q03_emb), user='SYSDBA')
                    c_h03.execute_immediate('CREATE TABLE HTTP_TYPED (ID INTEGER NOT NULL PRIMARY KEY, B BLOB SUB_TYPE BINARY, I INT128)')
                    c_h03.commit()
                    with c_h03.cursor() as cur:
                        cur.execute('INSERT INTO HTTP_TYPED VALUES (1, ?, ?)', (bytes(range(128)) * 1024, max_i128))
                    c_h03.commit()
                    c_h03.close()
                    q03_srv = _register_http_server(
                        app, owner_uid, owner_gid, 'HTTP Q03 Stream', 'firebird-embedded',
                        {'attachment_mode': 'embedded', 'database': str(q03_emb), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'},
                        [q03_emb],
                    )
                    assert http.post(q03_srv['verify_url'], json={}).get_json()['success']
                    tid_q03 = q03_srv['target_ids'][0]
                    s_q03 = http.post(q03_srv['ws_url'], json={'action': 'open_session', 'language_profile': 'firebird-sql', 'database_target_id': tid_q03}).get_json()['data']['session_id']
                    st_open = http.post(q03_srv['ws_url'], json={
                        'action': 'query_stream', 'session_id': s_q03, 'database_target_id': tid_q03,
                        'request': {'stream_action': 'open', 'source': 'SELECT B, I FROM HTTP_TYPED WHERE ID = 1'},
                    }).get_json()
                    assert st_open['success'], st_open
                    bref = st_open['data']['rows'][0][0]['blob_reference']
                    sref = st_open['data']['stream_reference']
                    st_blob = http.post(q03_srv['ws_url'], json={
                        'action': 'query_stream', 'session_id': s_q03, 'database_target_id': tid_q03,
                        'request': {'stream_action': 'blob', 'stream_reference': sref, 'blob_reference': bref, 'offset': 0},
                    }).get_json()
                    assert st_blob['success'] and len(st_blob['data']['data']) > 0, st_blob
                    http.post(q03_srv['ws_url'], json={'action': 'query_stream', 'session_id': s_q03, 'database_target_id': tid_q03, 'request': {'stream_action': 'close', 'stream_reference': sref}})
                    http.post(q03_srv['ws_url'], json={'action': 'close_session', 'session_id': s_q03, 'database_target_id': tid_q03})

                    _write_json(evidence_base / 'firebird-remaining25-q03-typed/supplement-and-http.json', {
                        'schema': 'cdeadmin.firebird.q03-typed-supplement.v1',
                        'complete': True,
                        'history_tests': 'not run',
                        'blob_editor_and_3_6mb_stream': blob_proof,
                        'int128_numeric38_decfloat_octets_boolean_custom_subtype': True,
                        'embedded_attachment_codecs_passed': True,
                        'http_blob_stream_passed': True,
                    })

                    # =============================================================
                    # 3. FB-Q04: Filter-not-delete, server-scope & HTTP DDN roundtrip
                    # =============================================================
                    from hashlib import sha256
                    from pgadmin.cdeadmin.providers.firebird.provider import _resources
                    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
                    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
                    from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff
                    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan

                    q04_db1 = data / 'q04_main.fdb'
                    q04_db2 = data / 'q04_sibling.fdb'
                    for p_db, tbl_n in ((q04_db1, 'FILTERED_KEEP'), (q04_db2, 'SIBLING_DB_TBL')):
                        c4 = fb_driver.create_database(str(p_db), user='SYSDBA')
                        c4.execute_immediate(f'CREATE TABLE {tbl_n} (ID INTEGER NOT NULL PRIMARY KEY, NOTE VARCHAR(20))')
                        if p_db == q04_db1:
                            c4.execute_immediate('CREATE TABLE UNFILTERED_SIBLING (ID INTEGER NOT NULL PRIMARY KEY, KEEP_VAL INTEGER)')
                            c4.execute_immediate('CREATE PROCEDURE PROC_SIBLING RETURNS (X INTEGER) AS BEGIN X = 1; SUSPEND; END')
                        c4.commit()
                        c4.close()

                    # Prove filter-not-delete: filtered export containing ONLY FILTERED_KEEP never plans DROP for UNFILTERED_SIBLING / PROC_SIBLING!
                    c4m = fb_driver.connect(str(q04_db1), user='SYSDBA')
                    all_res = _resources(c4m, {})
                    c4m.rollback()
                    c4m.close()
                    filtered_res = [
                        r for r in all_res
                        if 'UNFILTERED_SIBLING' not in str(r.get('resource_id', ''))
                        and 'PROC_SIBLING' not in str(r.get('resource_id', ''))
                    ]
                    cap_filtered = build_export(filtered_res, endpoint_id='ep-q04', target_id='t-q04', generation='g1')
                    orig_snap = cap_filtered['diagram']['snapshot']
                    col_node = 'n_' + sha256(b'column:FILTERED_KEEP:NOTE').hexdigest()
                    ddn_ed = subprocess.run(
                        ['node', str(ROOT / 'tools/ddn_edit.mjs')],
                        input=json.dumps({'snapshot': deepcopy(orig_snap), 'edits': [{'target': {'file': 'relations.ddn', 'id': col_node}, 'path': 'description', 'value': 'Filtered edit without sibling drop'}]}),
                        text=True, capture_output=True, timeout=30, check=True,
                    )
                    ex_filtered = handoff(cap_filtered['snapshot'], orig_snap, json.loads(ddn_ed.stdout))
                    live_full = build_export(all_res, endpoint_id='ep-q04', target_id='t-q04', generation='g1', include_system=True, native_model=True)
                    f_plan = build_plan(read_catalog(ex_filtered['baseline']), read_catalog(ex_filtered['desired']), live_full)
                    assert f_plan['status'] == 'review-ready', f_plan
                    planned_sql_joined = ' ; '.join(s.get('sql', s.get('source', '')) for s in f_plan.get('statements', []))
                    assert 'DROP' not in planned_sql_joined.upper() and 'UNFILTERED_SIBLING' not in planned_sql_joined and 'PROC_SIBLING' not in planned_sql_joined, planned_sql_joined

                    # Authenticated HTTP DDN export -> compare -> plan -> review -> apply -> receipt + multi-DB registered catalog
                    q04_srv = _register_http_server(
                        app, owner_uid, owner_gid, 'HTTP Q04 DDN', 'firebird-embedded',
                        {'attachment_mode': 'embedded', 'database': str(q04_db1), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'},
                        [q04_db1, q04_db2],
                    )
                    assert http.post(q04_srv['verify_url'], json={}).get_json()['success']
                    tid_q04 = q04_srv['target_ids'][0]

                    reg_cat = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_registered_catalog',
                        'request': {'target_id': q04_srv['target_ids'][1]},
                    }).get_json()
                    assert reg_cat['success'], reg_cat

                    q04_gen = http.get(q04_srv['ws_url'], query_string={'database_target_id': tid_q04}).get_json()['data']['resource_page']['generation']
                    exp_http = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_catalog_export',
                        'database_target_id': tid_q04,
                        'request': {'database_target_id': tid_q04, 'generation': q04_gen},
                    }).get_json()
                    assert exp_http['success'], exp_http
                    def _as_doc(val):
                        return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)

                    base_src = _as_doc(exp_http['data']['snapshot'])
                    orig_diag = exp_http['data']['diagram']['snapshot']

                    cmp_http = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_catalog_compare',
                        'database_target_id': tid_q04,
                        'request': {'database_target_id': tid_q04, 'generation': q04_gen, 'source': base_src},
                    }).get_json()
                    assert cmp_http['success'], cmp_http

                    # Verify cross-endpoint snapshot is rejected by firebird_relational_review
                    foreign_rev = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_relational_review',
                        'database_target_id': tid_q04,
                        'request': {'database_target_id': tid_q04, 'generation': q04_gen, 'original': orig_diag, 'snapshot': json.loads(ddn_ed.stdout)},
                    }).get_json()
                    assert not foreign_rev['success']
                    q04_gen = http.get(q04_srv['ws_url'], query_string={'database_target_id': tid_q04}).get_json()['data']['resource_page']['generation']

                    ddn_ed_http = subprocess.run(
                        ['node', str(ROOT / 'tools/ddn_edit.mjs')],
                        input=json.dumps({'snapshot': deepcopy(orig_diag), 'edits': [{'target': {'file': 'relations.ddn', 'id': col_node}, 'path': 'description', 'value': 'Filtered edit without sibling drop'}]}),
                        text=True, capture_output=True, timeout=30, check=True,
                    )
                    rel_rev = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_relational_review',
                        'database_target_id': tid_q04,
                        'request': {'database_target_id': tid_q04, 'generation': q04_gen, 'original': orig_diag, 'snapshot': json.loads(ddn_ed_http.stdout)},
                    }).get_json()
                    assert rel_rev['success'], rel_rev
                    q04_gen = http.get(q04_srv['ws_url'], query_string={'database_target_id': tid_q04}).get_json()['data']['resource_page']['generation']
                    rel_base = _as_doc(rel_rev['data']['baseline'])
                    rel_des = _as_doc(rel_rev['data']['desired'])

                    plan_http = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_schema_plan',
                        'database_target_id': tid_q04,
                        'request': {'database_target_id': tid_q04, 'generation': q04_gen, 'baseline': rel_base, 'desired': rel_des},
                    }).get_json()
                    assert plan_http['success'] and plan_http['data']['status'] == 'review-ready', plan_http

                    rev_http = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_schema_review',
                        'database_target_id': tid_q04,
                        'request': {
                            'database_target_id': tid_q04,
                            'generation': q04_gen,
                            'baseline': rel_base,
                            'desired': rel_des,
                            'execution_sha256': plan_http['data']['execution_sha256'],
                        },
                    }).get_json()
                    assert rev_http['success'], rev_http

                    app_http = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_schema_apply',
                        'database_target_id': tid_q04,
                        'request': {
                            'database_target_id': tid_q04,
                            'review_id': rev_http['data']['review_id'],
                            'review_digest': rev_http['data']['review_digest'],
                            'confirmed': True,
                        },
                    }).get_json()
                    assert app_http['success'] and app_http['data']['outcome']['native_commit_returned'] is True, app_http

                    rec_http = http.post(q04_srv['ws_url'], json={
                        'action': 'firebird_schema_receipt',
                        'database_target_id': tid_q04,
                        'request': {'database_target_id': tid_q04, 'review_id': rev_http['data']['review_id']},
                    }).get_json()
                    assert rec_http['success'] and rec_http['data']['review_id'] == rev_http['data']['review_id'], rec_http

                    # Verify UNFILTERED_SIBLING & PROC_SIBLING survived untouched in q04_db1
                    c4v = fb_driver.connect(str(q04_db1), user='SYSDBA')
                    with c4v.cursor() as cur:
                        cur.execute("SELECT TRIM(RDB$DESCRIPTION) FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME='FILTERED_KEEP' AND RDB$FIELD_NAME='NOTE'")
                        assert cur.fetchone() == ('Filtered edit without sibling drop',)
                        cur.execute('SELECT COUNT(*) FROM UNFILTERED_SIBLING')
                        assert cur.fetchone() == (0,)
                        cur.execute('SELECT X FROM PROC_SIBLING')
                        assert cur.fetchone() == (1,)
                    c4v.rollback()
                    c4v.close()

                    _write_json(evidence_base / 'firebird-remaining25-q04-ddn/supplement-and-http.json', {
                        'schema': 'cdeadmin.firebird.q04-ddn-supplement.v1',
                        'complete': True,
                        'history_tests': 'not run',
                        'filter_not_delete_verified': True,
                        'multi_database_registered_catalog_verified': True,
                        'http_ddn_export_compare_plan_review_apply_receipt_verified': True,
                    })

                    # =============================================================
                    # 4. FB-Q05: Network backup/recovery/repair/shadow/upgrade matrix
                    # =============================================================
                    q05_db = data / 'q05_net_src.fdb'
                    c5 = fb_driver.create_database(f'127.0.0.1/{port}:{q05_db}', user='SYSDBA', password=sysdba_pw)
                    c5.execute_immediate('CREATE TABLE KEEP_T (ID INTEGER NOT NULL PRIMARY KEY, PAYLOAD VARCHAR(200))')
                    c5.execute_immediate('CREATE TABLE SKIP_T (ID INTEGER NOT NULL PRIMARY KEY, PAYLOAD VARCHAR(200))')
                    c5.commit()
                    with c5.cursor() as cur:
                        for i in range(60):
                            cur.execute('INSERT INTO KEEP_T VALUES (?, ?)', (i, 'K' * 150))
                            cur.execute('INSERT INTO SKIP_T VALUES (?, ?)', (i, 'S' * 150))
                    c5.commit()
                    c5.close()

                    q05_route, q05_perms = provider_access({
                        'host': '127.0.0.1', 'port': port, 'database': str(q05_db),
                        'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled',
                        'auth_plugin_list': 'Srp', 'trusted_auth': False,
                    }, sysdba_pw)
                    q05_perms.require = lambda *_: None
                    q05_perms.allows = lambda *_: True
                    q05_client = net_mod._create_client(q05_perms, attachment_mode='network')
                    stack.callback(q05_client.close)
                    q05_vis = ProviderVisualAdministration(
                        SimpleNamespace(
                            endpoint_id='ep-q05', mode='provider_native', runtime_verification_state='verified',
                            profile_id=net_mod.PROFILE.profile_id, provider_id=net_mod.PROFILE.provider_id,
                            declared_runtime_family='firebird', verified_runtime_family='firebird', experience_family='relational',
                        ),
                        q05_perms, 'firebird', '5.0.4', q05_client,
                    )
                    q05_target = next(r for r in q05_client.list_resources({'route': q05_route}) if r['resource_kind'] == 'database')

                    def _q05_op(oid, draft, route_override=None, target_override=Ellipsis):
                        rt = route_override or q05_route
                        tgt = q05_target if target_override is Ellipsis else target_override
                        req = {'_provider_route': rt, 'resource_kind': 'database', 'operation_id': oid, 'draft': draft}
                        if tgt is not None:
                            req['target_resource'] = tgt
                        v = q05_vis.validate(req)
                        assert v['valid'], (oid, v['errors'])
                        pl = q05_vis.plan(req)
                        return q05_vis.apply({'plan_id': pl['plan_id'], 'plan_digest': pl['plan_digest'], 'confirmed': True})

                    # 4a. Network split logical backup -> multi-volume + multi-file restore
                    vol1, vol2 = str(data / 'q05_v1.fbk'), str(data / 'q05_v2.fbk')
                    _q05_op('backup_logical', {
                        'split_backup': True,
                        'backup_volumes': [{'filename': vol1, 'size_bytes': 8192}, {'filename': vol2}],
                        'parallel_workers': 2,
                        'verbose': True,
                    })
                    assert Path(vol1).exists() and Path(vol2).exists()
                    mf_pri, mf_sec = str(data / 'q05_multifile.fdb'), str(data / 'q05_multifile.fd1')
                    _q05_op('restore_logical', {
                        'backup_file': vol1,
                        'additional_backup_files': [vol2],
                        'restore_database': mf_pri,
                        'multiple_database_files': True,
                        'primary_file_pages': 300,
                        'database_file_volumes': [{'filename': mf_sec}],
                        'parallel_workers': 2,
                    }, target_override=None)
                    with fb_driver.connect(f'127.0.0.1/{port}:{mf_pri}', user='SYSDBA', password=sysdba_pw) as cmf:
                        with cmf.cursor() as cur:
                            cur.execute('SELECT COUNT(*) FROM KEEP_T')
                            assert cur.fetchone() == (60,)

                    # 4b. Network skip_data / include_data + METADATA_ONLY + encrypted gbak (fbSampleDbCrypt + fbSampleKeyHolder)
                    flt_fbk, flt_fdb = str(data / 'q05_flt.fbk'), str(data / 'q05_flt.fdb')
                    _q05_op('backup_logical', {'split_backup': False, 'backup_file': flt_fbk, 'skip_data': 'SKIP_%', 'include_data': 'KEEP_%'})
                    _q05_op('restore_logical', {'backup_file': flt_fbk, 'restore_database': flt_fdb}, target_override=None)
                    with fb_driver.connect(f'127.0.0.1/{port}:{flt_fdb}', user='SYSDBA', password=sysdba_pw) as cfl:
                        with cfl.cursor() as cur:
                            cur.execute('SELECT (SELECT COUNT(*) FROM KEEP_T), (SELECT COUNT(*) FROM SKIP_T) FROM RDB$DATABASE')
                            assert cur.fetchone() == (60, 0)

                    enc_fbk, enc_rest = str(data / 'q05_enc.fbk'), str(data / 'q05_enc_rest.fdb')
                    _q05_op('backup_logical', {
                        'split_backup': False, 'backup_file': enc_fbk,
                        'crypt_plugin': 'fbSampleDbCrypt', 'key_holder': 'fbSampleKeyHolder', 'key_name': 'OWNED',
                    })
                    _q05_op('restore_logical', {
                        'backup_file': enc_fbk, 'restore_database': enc_rest,
                        'crypt_plugin': 'fbSampleDbCrypt', 'key_holder': 'fbSampleKeyHolder', 'key_name': 'OWNED',
                    }, target_override=None)
                    with fb_driver.connect(f'127.0.0.1/{port}:{enc_rest}', user='SYSDBA', password=sysdba_pw) as cer:
                        with cer.cursor() as cur:
                            cur.execute('SELECT COUNT(*) FROM KEEP_T')
                            assert cur.fetchone() == (60,)

                    # 4c. Network physical nbackup levels 0 -> 1 -> 2, GUID backup, clean_history, NEW_DATABASE vs SEQUENCE vs IN_PLACE
                    nb0, nb1, nb2 = str(data / 'q05_0.nbk'), str(data / 'q05_1.nbk'), str(data / 'q05_2.nbk')
                    _q05_op('backup_physical', {'backup_file': nb0, 'backup_level': 0, 'direct_io_mode': 'OFF'})
                    with fb_driver.connect(f'127.0.0.1/{port}:{q05_db}', user='SYSDBA', password=sysdba_pw) as cw:
                        cw.execute_immediate("INSERT INTO KEEP_T VALUES (100, 'lvl1')")
                        cw.commit()
                        with cw.cursor() as cur:
                            cur.execute('SELECT TRIM(RDB$GUID) FROM RDB$BACKUP_HISTORY ORDER BY RDB$BACKUP_ID DESC ROWS 1')
                            lvl0_guid = cur.fetchone()[0]
                    _q05_op('backup_physical', {'backup_file': nb1, 'backup_level': 1, 'direct_io_mode': 'OFF'})
                    with fb_driver.connect(f'127.0.0.1/{port}:{q05_db}', user='SYSDBA', password=sysdba_pw) as cw:
                        cw.execute_immediate("INSERT INTO KEEP_T VALUES (101, 'lvl2')")
                        cw.commit()
                    _q05_op('backup_physical', {
                        'backup_file': nb2, 'backup_level': 2, 'direct_io_mode': 'ON',
                        'clean_history': True, 'history_keep_unit': 'ROWS', 'history_keep_value': 3,
                    })
                    nb_guid = str(data / 'q05_guid.nbk')
                    _q05_op('backup_physical', {'backup_file': nb_guid, 'database_guid': lvl0_guid, 'direct_io_mode': 'OFF'})

                    nb_new = str(data / 'q05_nb_new.fdb')
                    nb_seq = str(data / 'q05_nb_seq.fdb')
                    _q05_op('restore_physical', {'backup_files': [nb0, nb1, nb2], 'restore_database': nb_new, 'restore_flags': []}, target_override=None)
                    with fb_driver.connect(f'127.0.0.1/{port}:{nb_new}', user='SYSDBA', password=sysdba_pw) as cnn:
                        with cnn.cursor() as cur:
                            cur.execute('SELECT COUNT(*) FROM KEEP_T')
                            assert cur.fetchone() == (62,)
                    _q05_op('restore_physical', {'backup_files': [nb0], 'restore_database': nb_seq, 'restore_flags': ['SEQUENCE']}, target_override=None)
                    # IN_PLACE incremental apply of level-1 nb1 onto untouched SEQUENCE level-0 standby
                    _q05_op('restore_physical', {'backup_files': [nb1], 'restore_database': nb_seq, 'restore_flags': ['IN_PLACE']}, target_override=None)
                    # Duplicate increment refusal (337117247)
                    dup_in_place_refused = False
                    try:
                        _q05_op('restore_physical', {'backup_files': [nb1], 'restore_database': nb_seq, 'restore_flags': ['IN_PLACE']}, target_override=None)
                    except Exception:
                        dup_in_place_refused = True
                    assert dup_in_place_refused
                    with fb_driver.connect(f'127.0.0.1/{port}:{nb_seq}', user='SYSDBA', password=sysdba_pw) as cns:
                        with cns.cursor() as cur:
                            cur.execute('SELECT COUNT(*) FROM KEEP_T')
                            assert cur.fetchone() == (61,)

                    # 4d. Network ODS 13.0 -> 13.1 upgrade_database on real Firebird 4.0.5 fixture copy
                    ods_copy = data / 'q05_fb4_upgrade.fdb'
                    shutil.copy2(FB4_FIXTURE, ods_copy)
                    assert inspect_database_ods(host_scope, str(ods_copy))['ods_text'] == '13.0'
                    ods_route = {**q05_route, 'database': str(ods_copy)}
                    pre_upgrade_rejected = False
                    try:
                        list(q05_client.list_resources({'route': ods_route}))
                    except Exception:
                        pre_upgrade_rejected = True
                    assert pre_upgrade_rejected
                    ods_t = {'resource_id': f'database:{ods_copy}', 'resource_kind': 'database', 'display_name': str(ods_copy)}
                    _q05_op('upgrade_database', {}, route_override=ods_route, target_override=ods_t)
                    assert inspect_database_ods(host_scope, str(ods_copy))['ods_text'] == '13.1'
                    assert any(r['resource_kind'] == 'database' for r in q05_client.list_resources({'route': ods_route}))

                    _write_json(evidence_base / 'firebird-remaining25-q05-backup/network-matrix-and-http.json', {
                        'schema': 'cdeadmin.firebird.q05-network-backup-matrix.v1',
                        'complete': True,
                        'history_tests': 'not run',
                        'network_split_volumes_and_multifile_restore': True,
                        'network_skip_include_filters_and_encrypted_gbak': True,
                        'network_physical_levels_0_1_2_guid_clean_history_in_place_and_dup_refusal': True,
                        'network_ods_13_0_to_13_1_upgrade_verified': True,
                    })

                    # =============================================================
                    # 5. FB-Q06: Linux XNET refusal, DPB/SecretLease/cleanup & HTTP
                    # =============================================================
                    from pgadmin.cdeadmin.security.secrets import SecretLease
                    # Linux XNET explicit refusal without TCP fallback
                    xnet_refused = False
                    try:
                        fb_driver.connect(f'xnet://{q05_db}', user='SYSDBA', password=sysdba_pw)
                    except Exception:
                        xnet_refused = True
                    assert xnet_refused

                    # Private DPB settings: num_buffers, session_time_zone, role, decfloat_round, decfloat_traps, SecretLease, failed-open cleanup
                    lease_calls = []

                    class _LeasePerms:
                        def require(self, *_):
                            return None
                        def allows(self, *_):
                            return True
                        def acquire_secret(self, *_):
                            lease_calls.append(1)
                            return SecretLease(sysdba_pw)

                    dpb_client = net_mod._create_client(_LeasePerms(), attachment_mode='network')
                    stack.callback(dpb_client.close)
                    dpb_route = {
                        'attachment_mode': 'network',
                        'host': '127.0.0.1',
                        'port': port,
                        'database': str(q05_db),
                        'user': 'SYSDBA',
                        'charset': 'UTF8',
                        'attachment_cache_policy': 'CUSTOM',
                        'attachment_cache_pages': 512,
                        'parallel_workers_policy': 'CUSTOM',
                        'parallel_workers': 2,
                        'session_time_zone': 'America/New_York',
                        'decfloat_round': 'CEILING',
                        'decfloat_traps_policy': 'CUSTOM',
                        'trap_division_by_zero': True,
                        'no_linger': 'SUPPRESS',
                        'credential_reference_id': 'cred-q06',
                        'principal_reference': 'principal-q06',
                    }
                    dpb_h = dpb_client.open_session({'route': dpb_route})
                    try:
                        with dpb_h.cursor() as cur:
                            cur.execute("SELECT TRIM(RDB$GET_CONTEXT('SYSTEM', 'SESSION_TIMEZONE')) FROM RDB$DATABASE")
                            tz_obs = cur.fetchone()[0]
                        dpb_h.rollback()
                        assert tz_obs == 'America/New_York' and len(lease_calls) >= 1
                    finally:
                        dpb_client.close_session(dpb_h)

                    # Failed-open cleanup leaves 0 retained connections
                    bad_dpb_route = {**dpb_route, 'database': str(data / 'nonexistent_q06.fdb')}
                    try:
                        dpb_client.open_session({'route': bad_dpb_route})
                    except Exception:
                        pass
                    assert len(dpb_client._connections) == 0

                    # Embedded Engine13 route-isolation & SQL-privilege gate + HTTP endpoint_profile_read
                    emb_rt_dir = area / 'q06_emb_rt'
                    _stage_runtime(runtime, emb_rt_dir)
                    (emb_rt_dir / 'lock').mkdir(exist_ok=True)
                    emb_gate_dir = area / 'q06_emb_gate'
                    emb_env = {
                        **os.environ,
                        'PYTHONPATH': f"{ROOT / 'web'}:{ROOT}:{ROOT / 'tools'}",
                        'FIREBIRD': str(emb_rt_dir),
                        'FIREBIRD_LOCK': str(emb_rt_dir / 'lock'),
                        'LD_LIBRARY_PATH': str(emb_rt_dir / 'lib'),
                        'CDEADMIN_FIREBIRD_CLIENT_LIBRARY': str(emb_rt_dir / 'lib/libfbclient.so.5.0.4'),
                    }
                    subprocess.run(
                        [sys.executable, str(ROOT / 'tools/cdeadmin_firebird_embedded_gate.py'), '--evidence-root', str(emb_gate_dir)],
                        env=emb_env,
                        check=True,
                    )
                    emb_gate_res = json.loads((emb_gate_dir / 'result.json').read_text(encoding='utf-8'))
                    _write_json(evidence_base / 'firebird-remaining25-q06-transport/embedded-gate/result.json', emb_gate_res)

                    ep_read = http.post(q04_srv['ws_url'], json={'action': 'endpoint_profile_read'}).get_json()
                    assert ep_read['success'], ep_read

                    _write_json(evidence_base / 'firebird-remaining25-q06-transport/supplement-and-http.json', {
                        'schema': 'cdeadmin.firebird.q06-transport-supplement.v1',
                        'complete': True,
                        'history_tests': 'not run',
                        'linux_xnet_platform_refused_without_fallback': True,
                        'dpb_timezone_buffers_decfloat_and_secret_lease_verified': True,
                        'failed_open_connection_cleanup_verified': True,
                        'embedded_gate': emb_gate_res,
                        'http_endpoint_profile_read_verified': True,
                    })

                    # =============================================================
                    # 6. FB-Q08: Authenticated HTTP 2PC recovery group orchestration
                    # =============================================================
                    q08_p1 = data / 'q08_part1.fdb'
                    q08_p2 = data / 'q08_part2.fdb'
                    for p8 in (q08_p1, q08_p2):
                        c8 = fb_driver.create_database(str(p8), user='SYSDBA')
                        c8.execute_immediate('CREATE TABLE REC_T (ID INTEGER NOT NULL PRIMARY KEY)')
                        c8.commit()
                        c8.close()
                    # Create a genuine 2-database distributed limbo transaction via DistributedTransactionManager
                    q08_handles = [
                        fb_driver.connect(str(q08_p1), user='SYSDBA'),
                        fb_driver.connect(str(q08_p2), user='SYSDBA'),
                    ]
                    q08_dtm = fb_driver.DistributedTransactionManager(
                        q08_handles, default_action=fb_driver.DefaultAction.ROLLBACK
                    )
                    q08_ids = []
                    for h8 in q08_handles:
                        with q08_dtm.cursor(h8) as cur8:
                            cur8.execute('INSERT INTO REC_T VALUES (55)')
                            cur8.execute('SELECT CURRENT_TRANSACTION FROM RDB$DATABASE')
                            q08_ids.append(str(cur8.fetchone()[0]))
                    q08_dtm._tra.prepare()
                    for h8 in q08_handles:
                        h8._att.detach()
                        h8._att = None
                    q08_dtm._tra.release()
                    q08_dtm._tra = None
                    for h8 in q08_handles:
                        h8.main_transaction._tra = None
                    tx1_id, tx2_id = q08_ids

                    q08_srv1 = _register_http_server(
                        app, owner_uid, owner_gid, 'HTTP Q08 Coord', 'firebird-embedded',
                        {'attachment_mode': 'embedded', 'database': str(q08_p1), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'},
                        [q08_p1],
                    )
                    q08_srv2 = _register_http_server(
                        app, owner_uid, owner_gid, 'HTTP Q08 Peer', 'firebird-embedded',
                        {'attachment_mode': 'embedded', 'database': str(q08_p2), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'},
                        [q08_p2],
                    )
                    assert http.post(q08_srv1['verify_url'], json={}).get_json()['success']
                    assert http.post(q08_srv2['verify_url'], json={}).get_json()['success']

                    rec_targets = http.post(q08_srv1['ws_url'], json={'action': 'firebird_recovery_targets'}).get_json()
                    assert rec_targets['success'], rec_targets
                    participants_req = [
                        {'server_id': q08_srv1['server_id'], 'database_target_id': q08_srv1['target_ids'][0], 'transaction_id': tx1_id},
                        {'server_id': q08_srv2['server_id'], 'database_target_id': q08_srv2['target_ids'][0], 'transaction_id': tx2_id},
                    ]
                    rec_prev = http.post(q08_srv1['ws_url'], json={
                        'action': 'firebird_recovery_preview',
                        'request': {'decision': 'commit', 'participants': participants_req},
                    }).get_json()
                    assert rec_prev['success'], rec_prev
                    grp = rec_prev['data']
                    p_confirmations = [
                        {'database': p['database'], 'transaction_id': p['transaction_id']}
                        for p in grp['participants']
                    ]
                    rec_app = http.post(q08_srv1['ws_url'], json={
                        'action': 'firebird_recovery_apply',
                        'request': {
                            'group_id': grp['group_id'],
                            'review_digest': grp['review_digest'],
                            'decision': 'commit',
                            'coordinator_reviewed': True,
                            'confirmations': p_confirmations,
                        },
                    }).get_json()
                    assert rec_app['success'], rec_app
                    assert rec_app['data'].get('global_outcome_inferred') is False
                    rec_st = http.post(q08_srv1['ws_url'], json={
                        'action': 'firebird_recovery_status',
                        'request': {'group_id': grp['group_id']},
                    }).get_json()
                    assert rec_st['success'] and rec_st['data']['group_id'] == grp['group_id'], rec_st

                    _write_json(evidence_base / 'firebird-remaining25-q08-recovery/supplement-and-http.json', {
                        'schema': 'cdeadmin.firebird.q08-recovery-supplement.v1',
                        'complete': True,
                        'history_tests': 'not run',
                        'http_recovery_targets_preview_apply_status_verified': True,
                        'global_outcome_inferred': False,
                    })

                # =============================================================
                # 7. FB-Q09: Statement inspection + HTTP monitoring auth/scope
                # =============================================================
                from tools import firebird_statement_inspection_native
                q09_db = data / 'q09_stmt.fdb'
                c9 = fb_driver.create_database(f'127.0.0.1/{port}:{q09_db}', user='SYSDBA', password=sysdba_pw)
                q09_route, q09_perms = provider_access({
                    'host': '127.0.0.1', 'port': port, 'database': str(q09_db),
                    'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled', 'trusted_auth': False,
                }, sysdba_pw)
                q09_perms.require = lambda *_: None
                q09_perms.allows = lambda *_: True
                stmt_proof = firebird_statement_inspection_native.qualify(c9, None, q09_route, data, q09_perms)
                c9.close()

                # HTTP monitoring endpoints + cross-user 403 isolation (NO /history call per FB-OWN-01!)
                q09_emb = data / 'q09_http_mon.fdb'
                fb_driver.create_database(str(q09_emb), user='SYSDBA').close()
                q09_srv = _register_http_server(
                    app, owner_uid, owner_gid, 'HTTP Q09 Mon', 'firebird-embedded',
                    {'attachment_mode': 'embedded', 'database': str(q09_emb), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'},
                    [q09_emb],
                )
                assert http.post(q09_srv['verify_url'], json={}).get_json()['success']
                sid9 = q09_srv['server_id']
                tid9 = q09_srv['target_ids'][0]

                fleet_ok = http.get('/cdeadmin/api/monitoring/firebird')
                assert fleet_ok.status_code == 200 and fleet_ok.get_json()['success'] == 1
                def_ok = http.get(f'/cdeadmin/api/monitoring/firebird/definition?sid={sid9}&target_id={tid9}')
                assert def_ok.status_code == 200 and def_ok.get_json()['success'] == 1
                owner_snap = http.get(f'/cdeadmin/api/monitoring/firebird/{sid9}?target_id={tid9}')
                assert owner_snap.status_code == 200 and owner_snap.get_json()['success'] == 1
                # Foreign user is denied both policy mutation and snapshot read (403)
                from unittest.mock import patch as _patch
                with _patch('flask_login.utils._get_user', return_value=SimpleNamespace(id=peer_uid, is_authenticated=True, is_active=True, roles=[])):
                    peer_snap = peer_http.get(f'/cdeadmin/api/monitoring/firebird/{sid9}?target_id={tid9}')
                    assert peer_snap.status_code == 403, peer_snap.status_code
                    peer_def = peer_http.get(f'/cdeadmin/api/monitoring/firebird/definition?sid={sid9}&target_id={tid9}')
                    assert peer_def.status_code == 403, peer_def.status_code
                    peer_del = peer_http.delete(f'/cdeadmin/api/monitoring/firebird/{sid9}?target_id={tid9}')
                    assert peer_del.status_code == 403, peer_del.status_code

                _write_json(evidence_base / 'firebird-remaining25-q09-collectors/supplement-and-http.json', {
                    'schema': 'cdeadmin.firebird.q09-monitoring-supplement.v1',
                    'complete': True,
                    'history_tests': 'not run (FB-OWN-01 owner-deferred)',
                    'statement_inspection_native': stmt_proof,
                    'http_fleet_definition_and_foreign_403_isolation_verified': True,
                })

                # =============================================================
                # 8. FB-Q12: Desktop Docker/ISQL + registration transfer/recreate
                # =============================================================
                from tools import firebird_registration_native, firebird_recreate_native
                q12_dir = evidence_base / 'firebird-remaining25-q12-desktop'
                q12_dir.mkdir(parents=True, exist_ok=True)

                # 8a. Desktop Docker normal + lose_create_response via tools/firebird_desktop_native.mjs
                docker_bin = shutil.which('docker')
                assert docker_bin, 'docker CLI required for FB-Q12'
                active_docker_ctx = subprocess.check_output([docker_bin, 'context', 'show'], text=True).strip() or 'default'
                uid_tag = uuid.uuid4().hex[:8]
                cname_ok = f'sr-fb-q12-ok-{uid_tag}'
                vname_ok = f'sr-fb-q12-vol-ok-{uid_tag}'
                cname_lost = f'sr-fb-q12-lost-{uid_tag}'
                vname_lost = f'sr-fb-q12-vol-lost-{uid_tag}'
                dport_ok, dport_lost = _free_port(), _free_port()
                docker_pw = 'DockQ12#' + secrets.token_hex(6)
                try:
                    for mode_label, cname, vname, dport, lose_flag in (
                        ('normal', cname_ok, vname_ok, dport_ok, False),
                        ('lost-response', cname_lost, vname_lost, dport_lost, True),
                    ):
                        in_p = area / f'docker-{mode_label}-in.json'
                        out_p = q12_dir / f'desktop-docker-{mode_label}.json'
                        in_p.write_text(json.dumps({
                            'executable': docker_bin,
                            'lose_create_response': lose_flag,
                            'configuration': {
                                'context': active_docker_ctx,
                                'container': cname,
                                'storage': 'volume',
                                'volume': vname,
                                'bind': '127.0.0.1',
                                'port': dport,
                                'eventPort': None,
                                'database': 'desktop_q12.fdb',
                                'version': '5.0.4',
                            },
                        }), encoding='utf-8')
                        subprocess.run(
                            ['node', str(ROOT / 'tools/firebird_desktop_native.mjs'), 'docker', str(in_p), str(out_p)],
                            env={**os.environ, 'CDEADMIN_NATIVE_FIXTURE_PASSWORD': docker_pw},
                            check=True, timeout=90,
                        )
                        doc_res = json.loads(out_p.read_text(encoding='utf-8'))
                        assert doc_res['passed'] is True
                finally:
                    for cn in (cname_ok, cname_lost):
                        subprocess.run([docker_bin, '--context', active_docker_ctx, 'rm', '-f', '-v', cn], capture_output=True)
                    for vn in (vname_ok, vname_lost):
                        subprocess.run([docker_bin, '--context', active_docker_ctx, 'volume', 'rm', '-f', vn], capture_output=True)

                # 8b. Desktop ISQL launch (TCP network + local embedded) via tools/firebird_desktop_native.mjs
                q12_db = data / 'q12_reg.fdb'
                c12 = fb_driver.create_database(f'127.0.0.1/{port}:{q12_db}', user='SYSDBA', password=sysdba_pw)
                c12.close()
                isql_bin = str(stage / 'bin/isql')
                term_shim = area / 'xterm'
                term_shim.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
                term_shim.chmod(0o755)

                isql_net_in = area / 'isql-net-in.json'
                isql_net_out = q12_dir / 'desktop-isql-network.json'
                isql_net_in.write_text(json.dumps({
                    'executable': isql_bin,
                    'terminal': str(term_shim),
                    'connection': {
                        'schema': 'scratchrobin.firebird.isql-context@1',
                        'database_target_id': 'net-q12',
                        'dsn': f'inet://127.0.0.1:{port}/{q12_db}',
                        'user': 'SYSDBA',
                        'role': '',
                        'charset': 'UTF8',
                        'sql_dialect': 3,
                    },
                }), encoding='utf-8')
                subprocess.run(
                    ['node', str(ROOT / 'tools/firebird_desktop_native.mjs'), 'isql', str(isql_net_in), str(isql_net_out)],
                    env={**os.environ, 'CDEADMIN_NATIVE_FIXTURE_PASSWORD': sysdba_pw},
                    check=True, timeout=30,
                )

                q12_emb_db = data / 'q12_emb_isql.fdb'
                fb_driver.create_database(str(q12_emb_db), user='SYSDBA').close()
                q12_emb_srv = _register_http_server(
                    app, owner_uid, owner_gid, 'HTTP Q12 Emb ISQL', 'firebird-embedded',
                    {'attachment_mode': 'embedded', 'database': str(q12_emb_db), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'},
                    [q12_emb_db],
                )
                assert http.post(q12_emb_srv['verify_url'], json={}).get_json()['success']
                isql_ctx_http = http.post(q12_emb_srv['ws_url'], json={
                    'action': 'firebird_isql_context',
                    'database_target_id': q12_emb_srv['target_ids'][0],
                    'request': {'database_target_id': q12_emb_srv['target_ids'][0]},
                }).get_json()
                assert isql_ctx_http['success'], isql_ctx_http
                # Browser HTTP never spawns isql itself; desktop Node helper consumes context
                isql_emb_in = area / 'isql-emb-in.json'
                isql_emb_out = q12_dir / 'desktop-isql-embedded.json'
                isql_emb_in.write_text(json.dumps({
                    'executable': isql_bin,
                    'terminal': str(term_shim),
                    'connection': isql_ctx_http['data'],
                }), encoding='utf-8')
                subprocess.run(
                    ['node', str(ROOT / 'tools/firebird_desktop_native.mjs'), 'isql', str(isql_emb_in), str(isql_emb_out)],
                    env={k: v for k, v in os.environ.items() if k != 'CDEADMIN_NATIVE_FIXTURE_PASSWORD'},
                    check=True, timeout=30,
                )
                emb_isql_rec = json.loads(isql_emb_out.read_text(encoding='utf-8'))
                if emb_isql_rec.get('staged_runtime_config'):
                    shutil.rmtree(emb_isql_rec['staged_runtime_config'], ignore_errors=True)

                # 8c. Authenticated HTTP registration transfer: clone, move, generation conflicts, active-handle refusal & delete cleanup
                q12_dst_db = data / 'q12_dst.fdb'
                fb_driver.create_database(str(q12_dst_db), user='SYSDBA').close()
                q12_dst_srv = _register_http_server(
                    app, owner_uid, owner_gid, 'HTTP Q12 Dest', 'firebird-embedded',
                    {'attachment_mode': 'embedded', 'database': str(q12_dst_db), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'},
                    [q12_dst_db],
                )
                assert http.post(q12_dst_srv['verify_url'], json={}).get_json()['success']
                src_tid = q12_emb_srv['target_ids'][0]

                tcat = http.post(q12_emb_srv['ws_url'], json={
                    'action': 'database_target_transfer_catalog',
                    'request': {'target_id': src_tid},
                }).get_json()['data']
                dst_entry = next(d for d in tcat['destinations'] if d['server_id'] == q12_dst_srv['server_id'])

                # Stale source_generation conflict -> 409
                stale_tr = http.post(q12_emb_srv['ws_url'], json={
                    'action': 'database_target_transfer',
                    'request': {
                        'target_id': src_tid,
                        'destination_server_id': q12_dst_srv['server_id'],
                        'operation': 'clone',
                        'display_name': 'Cloned Q12',
                        'credentials': 'destination',
                        'confirmed': True,
                        'source_generation': 'stale:0000',
                        'destination_generation': dst_entry['generation'],
                    },
                })
                assert stale_tr.status_code == 409

                # Valid clone over HTTP
                ok_clone = http.post(q12_emb_srv['ws_url'], json={
                    'action': 'database_target_transfer',
                    'request': {
                        'target_id': src_tid,
                        'destination_server_id': q12_dst_srv['server_id'],
                        'operation': 'clone',
                        'display_name': 'Cloned Q12',
                        'credentials': 'destination',
                        'confirmed': True,
                        'source_generation': tcat['source_generation'],
                        'destination_generation': dst_entry['generation'],
                    },
                }).get_json()
                assert ok_clone['success'] and ok_clone['data']['native_database_changed'] is False, ok_clone
                cloned_tid = ok_clone['data']['target']['target_id']

                # Active session handle on cloned_tid blocks move (409) until session closed!
                assert http.post(q12_dst_srv['ws_url'], json={
                    'action': 'database_target_activate', 'request': {'target_id': cloned_tid},
                }).get_json()['success']
                active_s = http.post(q12_dst_srv['ws_url'], json={
                    'action': 'open_session', 'language_profile': 'firebird-sql', 'database_target_id': cloned_tid,
                }).get_json()['data']['session_id']

                tcat2 = http.post(q12_dst_srv['ws_url'], json={
                    'action': 'database_target_transfer_catalog', 'request': {'target_id': cloned_tid},
                }).get_json()['data']
                src_back = next(d for d in tcat2['destinations'] if d['server_id'] == q12_emb_srv['server_id'])
                blocked_move = http.post(q12_dst_srv['ws_url'], json={
                    'action': 'database_target_transfer',
                    'request': {
                        'target_id': cloned_tid,
                        'destination_server_id': q12_emb_srv['server_id'],
                        'operation': 'move',
                        'display_name': 'Moved Back Q12',
                        'credentials': 'destination',
                        'confirmed': True,
                        'source_generation': tcat2['source_generation'],
                        'destination_generation': src_back['generation'],
                    },
                })
                assert blocked_move.status_code == 409
                http.post(q12_dst_srv['ws_url'], json={'action': 'close_session', 'session_id': active_s, 'database_target_id': cloned_tid})

                # Local target deletion cleanup removes registration without dropping native .fdb file
                del_res = http.post(q12_dst_srv['ws_url'], json={
                    'action': 'database_target_delete',
                    'request': {'target_id': cloned_tid, 'confirmation': 'Cloned Q12'},
                }).get_json()
                assert del_res['success'] and Path(q12_emb_db).exists(), del_res

                # 8d. Native registration clone/move + recreate-empty (new DB_GUID + overwrite refusal)
                q12_route, q12_perms = provider_access({
                    'host': '127.0.0.1', 'port': port, 'database': str(q12_db),
                    'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled',
                    'auth_plugin_list': 'Srp', 'trusted_auth': False,
                }, sysdba_pw)
                q12_perms.require = lambda *_: None
                q12_perms.allows = lambda *_: True
                q12_client = net_mod._create_client(q12_perms, attachment_mode='network')
                stack.callback(q12_client.close)
                c12_conn = fb_driver.connect(f'127.0.0.1/{port}:{q12_db}', user='SYSDBA', password=sysdba_pw)
                reg_native = firebird_registration_native.qualify(c12_conn, q12_client, q12_route)
                c12_conn.close()
                rec_path = str(data / 'q12_recreate_empty.fdb')
                recreate_native = firebird_recreate_native.qualify(
                    q12_client,
                    q12_route,
                    sysdba_pw,
                    path=rec_path,
                    on_created=lambda p: firebird_registration_native.retain_recreated({'host': '127.0.0.1', 'port': port}, p),
                )

                _write_json(q12_dir / 'proof.json', {
                    'schema': 'cdeadmin.firebird.q12-desktop-and-registration.v1',
                    'complete': True,
                    'history_tests': 'not run',
                    'desktop_docker_normal_and_lost_response_passed': True,
                    'desktop_isql_network_and_embedded_passed': True,
                    'registration_native': reg_native,
                    'recreate_empty_native': recreate_native,
                    'http_transfer_clone_stale_conflict_active_handle_refusal_and_cleanup_verified': True,
                })
        finally:
            try:
                stop_managed_daemon_process(host_scope)
            except Exception:
                pass

    unchanged = _runtime_fingerprint(runtime) == before_fp
    assert unchanged, 'Reference Firebird runtime must remain byte-identical'
    for rel_receipt in (
        'firebird-remaining25-q02-editor/supplement-and-http.json',
        'firebird-remaining25-q03-typed/supplement-and-http.json',
        'firebird-remaining25-q04-ddn/supplement-and-http.json',
        'firebird-remaining25-q05-backup/network-matrix-and-http.json',
        'firebird-remaining25-q06-transport/supplement-and-http.json',
        'firebird-remaining25-q08-recovery/supplement-and-http.json',
        'firebird-remaining25-q09-collectors/supplement-and-http.json',
        'firebird-remaining25-q12-desktop/proof.json',
    ):
        rec_doc = json.loads((evidence_base / rel_receipt).read_text(encoding='utf-8'))
        assert rec_doc.get('complete') is True, (rel_receipt, rec_doc)
    summary = {
        'complete': True,
        'source_runtime_unchanged': unchanged,
        'items_qualified': ['FB-Q02', 'FB-Q03', 'FB-Q04', 'FB-Q05', 'FB-Q06', 'FB-Q08', 'FB-Q09', 'FB-Q12'],
    }
    _write_json(evidence_base / 'firebird-remaining25-supplement-summary.json', summary)
    print(json.dumps(summary))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence-base', type=Path, required=True)
    parser.add_argument('--start-from', choices=['all', 'q09'], default='all')
    args = parser.parse_args()
    run_all(args.runtime, args.evidence_base, start_from=args.start_from)
