#!/usr/bin/env python3
"""Verify production embedded attachment boundaries on an isolated local file.

Run in a fresh process with FIREBIRD, LD_LIBRARY_PATH and
CDEADMIN_FIREBIRD_CLIENT_LIBRARY selecting a complete Firebird 5 runtime.
No reference or demo database is opened or modified.

Platform qualification: this gate has native Linux evidence. Windows agents
must verify DLL/plugin discovery, drive/UNC containment, ACL-denied files,
file locking and dependency recovery. macOS agents must verify dylib/plugin
discovery, signing/quarantine restrictions and filesystem permissions. Do not
reuse Linux passes as evidence for either platform. The POSIX chmod case must
be replaced with a real ACL denial on Windows, never silently skipped.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import itertools
import os
from pathlib import Path
import tempfile
from threading import Barrier
import uuid

if __package__:
    from .cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
    from .cdeadmin_firebird_transaction_state_gate import verify_route
    from .cdeadmin_firebird_rounding_oracle import (
        MODES, observe_rounding, expected_rounding,
    )
    from .cdeadmin_firebird_traps_oracle import observe_traps
else:
    from cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
    from cdeadmin_firebird_transaction_state_gate import verify_route
    from cdeadmin_firebird_rounding_oracle import (
        MODES, observe_rounding, expected_rounding,
    )
    from cdeadmin_firebird_traps_oracle import observe_traps

from pgadmin.cdeadmin.core import EndpointContext, ProviderRegistry
from pgadmin.cdeadmin.providers.firebird.provider import (
    _create_client,
)
from pgadmin.cdeadmin.providers.firebird.embedded_provider import PROFILE
from pgadmin.cdeadmin.providers.firebird.decfloat_traps import TRAP_FIELDS
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


class LocalPermissions:
    def require(self, name, scope='endpoint'):
        if scope != 'endpoint' or name not in {
                'embedded_runtime', 'filesystem'}:
            raise PermissionError(name)

    def acquire_secret(self, *_args):
        raise AssertionError('Embedded attachment requested a secret')


def verify_provider(route):
    identity = str(uuid.uuid4())
    context = EndpointContext(
        endpoint_id=identity, mode='legacy_native',
        experience_family=PROFILE.engine_id, provider_id=PROFILE.provider_id,
        provider_version='0.1.0', profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version,
        target_adapter_id='firebird-embedded-client',
        target_adapter_version='owned-embedded-gate',
        pool_namespace=str(uuid.uuid4()),
        session_namespace=str(uuid.uuid4()),
        cache_namespace=str(uuid.uuid4()),
        diagnostic_namespace=str(uuid.uuid4()),
        effective_permissions=frozenset({
            'embedded_runtime', 'filesystem', 'data_read', 'administer'}))
    manifest_path = Path(__file__).resolve().parents[1] / (
        'web/pgadmin/cdeadmin/providers/firebird/'
        'embedded_provider_manifest.json')
    registry = ProviderRegistry()
    registry.register_package(
        json.loads(manifest_path.read_text()),
        'pgadmin.cdeadmin.providers.firebird.embedded_provider')
    provider = registry.resolve(context).instance
    try:
        discovery = provider.discover_endpoint({'route': route})
        assert discovery['verified_runtime']['version'] == '5.0.4'
        resources = provider.list_resources({'route': route})
        assert any(item['display_name'] == 'OWNED_PRIVATE'
                   for item in resources)
        assert not any(item['resource_kind'] == 'service-operation'
                       for item in resources)
        session = provider.open_session({'route': route})
        assert len(provider._sessions) == 1
        for operation in (provider.discover_endpoint, provider.open_session):
            try:
                operation({'route': {'host': '127.0.0.1', 'port': 1,
                                     'database': route['database']}})
            except RelationalClientError:
                pass
            else:
                raise AssertionError('Embedded provider accepted TCP request')
        assert len(provider._sessions) == 1
        provider.close_session({'session_id': session['session_id']})
        assert not provider._sessions
    finally:
        provider.client.close()


def verify_file_failures(client, route):
    """An open operation must neither bypass OS access nor create a file."""
    database = Path(route['database'])
    original_mode = database.stat().st_mode & 0o777

    def refused(candidate):
        try:
            handle = client.open_session({'route': candidate})
        except RelationalClientError:
            return
        try:
            raise AssertionError('Invalid database file was attached')
        finally:
            client.close_session(handle)

    try:
        database.chmod(0)
        refused(route)
    finally:
        database.chmod(original_mode)
    missing = database.with_name('does-not-exist.fdb')
    refused({**route, 'database': str(missing)})
    assert not missing.exists()
    malformed = database.with_name('not-a-database.fdb')
    payload = b'Owned negative test fixture, not a Firebird database.\n'
    malformed.write_bytes(payload)
    refused({**route, 'database': str(malformed)})
    assert malformed.read_bytes() == payload
    # The same client must remain usable after all rejected attachments.
    handle = client.open_session({'route': route})
    try:
        cursor = handle.cursor()
        cursor.execute('SELECT ID FROM OWNED_PRIVATE')
        assert cursor.fetchall() == [(2,)]
        handle.rollback()
    finally:
        client.close_session(handle)


def verify_concurrent_identities(route):
    """Overlap real attachments; never share a native handle across threads."""
    barrier = Barrier(3, timeout=30)

    def worker(identity):
        client = _create_client(LocalPermissions())
        handle = None
        try:
            handle = client.open_session({
                'route': {**route, 'user': identity}})
            cursor = handle.cursor()
            cursor.execute('SELECT CURRENT_USER FROM RDB$DATABASE')
            assert cursor.fetchone()[0].strip() == identity
            barrier.wait()
            if identity == 'OWNED_NO_GRANTS':
                try:
                    cursor.execute('SELECT ID FROM OWNED_PRIVATE')
                except client.module.DatabaseError:
                    pass
                else:
                    raise AssertionError(
                        'Concurrent identity inherited grants')
            else:
                cursor.execute('SELECT ID FROM OWNED_PRIVATE')
                assert cursor.fetchall() == [(2,)]
                if identity == 'OWNED_READ_ONLY':
                    try:
                        cursor.execute('INSERT INTO OWNED_PRIVATE VALUES (99)')
                    except client.module.DatabaseError:
                        pass
                    else:
                        raise AssertionError('SELECT grant allowed INSERT')
                else:
                    cursor.execute('INSERT INTO OWNED_PRIVATE VALUES (100)')
            handle.rollback()
            barrier.wait()
            cursor.execute('SELECT CURRENT_USER FROM RDB$DATABASE')
            assert cursor.fetchone()[0].strip() == identity
            handle.rollback()
            return identity
        except BaseException:
            barrier.abort()
            raise
        finally:
            try:
                if handle is not None:
                    client.close_session(handle)
            finally:
                client.close()

    identities = ('SYSDBA', 'OWNED_READ_ONLY', 'OWNED_NO_GRANTS')
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker, identity)
                   for identity in identities]
        # Collect every worker outcome before reporting the combined failure.
        outcomes, failures = [], []
        for future in futures:
            try:
                outcomes.append(future.result())
            except Exception as exc:
                failures.append(f'{type(exc).__name__}: {exc}')
        assert not failures, failures
        assert tuple(outcomes) == identities


def verify_transaction_flags(route):
    result = {'cases': [], 'failures': [], 'complete': False}
    observer = _create_client(LocalPermissions())

    def rows():
        handle = observer.open_session({'route': route})
        try:
            with handle.cursor() as cursor:
                cursor.execute('SELECT ID FROM OWNED_FLAGS ORDER BY ID')
                return cursor.fetchall()
        finally:
            observer.close_session(handle)

    try:
        for auto_commit, no_auto_undo, ignore_limbo in itertools.product(
                (False, True), repeat=3):
            flags = {'transaction_auto_commit': auto_commit,
                     'transaction_no_auto_undo': no_auto_undo,
                     'transaction_ignore_limbo': ignore_limbo}
            client = _create_client(LocalPermissions())
            handle = None
            try:
                handle = client.open_session({'route': {**route, **flags}})
                with handle.cursor() as cursor:
                    cursor.execute(
                        'SELECT MON$AUTO_COMMIT, MON$AUTO_UNDO '
                        'FROM MON$TRANSACTIONS WHERE '
                        'MON$TRANSACTION_ID = CURRENT_TRANSACTION')
                    assert cursor.fetchone() == (
                        int(auto_commit), int(not no_auto_undo))
                client.control_transaction(handle, 'rollback')
                with handle.cursor() as cursor:
                    cursor.execute('INSERT INTO OWNED_FLAGS VALUES (43)')
                expected = [(43,)] if auto_commit else []
                before = rows()
                assert before == expected
                client.control_transaction(handle, 'rollback')
                after = rows()
                assert after == expected
                result['cases'].append({
                    **flags, 'visible_before_rollback': before,
                    'visible_after_rollback': after})
            except Exception as exc:
                result['failures'].append({
                    **flags, 'error_type': type(exc).__name__,
                    'message': str(exc)})
            finally:
                try:
                    if handle is not None:
                        client.close_session(handle)
                finally:
                    client.close()
                cleanup = observer.open_session({'route': route})
                try:
                    with cleanup.cursor() as cursor:
                        cursor.execute('DELETE FROM OWNED_FLAGS')
                    observer.control_transaction(cleanup, 'commit')
                finally:
                    observer.close_session(cleanup)
        assert rows() == []
    finally:
        observer.close()
    result['complete'] = len(result['cases']) == 8 and not result['failures']
    return result


def verify_limbo(route):
    """Prepare, detach and explicitly recover a transaction in the owned DB."""
    client = _create_client(LocalPermissions())
    prepared = client._connect({'route': route})
    detached = False
    prepared_id = None
    result = {'cases': [], 'failures': [], 'complete': False}
    try:
        with prepared.cursor() as cursor:
            cursor.execute('INSERT INTO OWNED_FLAGS VALUES (44)')
        prepared.commit()
        with prepared.cursor() as cursor:
            cursor.execute('UPDATE OWNED_FLAGS SET ID = 45 WHERE ID = 44')
            assert cursor.rowcount == 1
        prepared_id = prepared.main_transaction.info.id
        native = prepared.main_transaction._tra
        native.prepare()
        prepared._att.detach()
        prepared._att = None
        detached = True
        native.release()
        prepared.main_transaction._tra = None
        observer = client._connect({'route': route})
        try:
            assert prepared_id in observer.info.get_info(
                client.module.DbInfoCode.LIMBO)
        finally:
            observer.close()
        for ignore in (False, True):
            handle = None
            case = {'ignore_limbo': ignore}
            try:
                handle = client.open_session({'route': {
                    **route, 'transaction_ignore_limbo': ignore,
                    'transaction_access': 'READ',
                    'transaction_isolation': 'SNAPSHOT',
                    'transaction_lock_timeout': 0,
                    'statement_timeout_ms': 1000}})
                try:
                    with handle.cursor() as cursor:
                        cursor.execute('SELECT ID FROM OWNED_FLAGS')
                        rows = cursor.fetchall()
                except client.module.DatabaseError as exc:
                    assert not ignore and 335544459 in exc.gds_codes
                    case['native_codes'] = list(exc.gds_codes)
                else:
                    assert ignore and rows == [(44,)]
                    case['committed_version_returned'] = True
                result['cases'].append(case)
            except Exception as exc:
                result['failures'].append({
                    **case, 'error_type': type(exc).__name__,
                    'message': str(exc)})
            finally:
                if handle is not None:
                    client.close_session(handle)
    finally:
        try:
            if detached:
                recovery = client._connect({'route': route})
                try:
                    native = recovery._att.reconnect_transaction(
                        prepared_id.to_bytes(8, 'little'))
                    native.rollback()
                    assert prepared_id not in recovery.info.get_info(
                        client.module.DbInfoCode.LIMBO)
                    with recovery.cursor() as cursor:
                        cursor.execute('SELECT ID FROM OWNED_FLAGS')
                        assert cursor.fetchall() == [(44,)]
                        cursor.execute('DELETE FROM OWNED_FLAGS')
                    recovery.commit()
                    result['explicit_recovery_verified'] = True
                finally:
                    recovery.close()
            elif prepared.main_transaction.is_active():
                prepared.rollback()
        finally:
            prepared.close()
            client.close()
    result['complete'] = (len(result['cases']) == 2 and
                          not result['failures'] and
                          result.get('explicit_recovery_verified', False))
    return result


def verify_session_options(route):
    result = {'cases': [], 'failures': [], 'complete': False}
    client = _create_client(LocalPermissions())
    try:
        for charset, zone, timeout in itertools.product(
                ('UTF8', 'WIN1252', 'NONE'),
                ('UTC', 'Europe/Paris'), (0, 1200)):
            case = {'charset': charset, 'session_time_zone': zone,
                    'statement_timeout_ms': timeout,
                    'session_idle_timeout_seconds': 90 if timeout else 0}
            handle = None
            try:
                handle = client.open_session({'route': {**route, **case}})
                assert not handle.main_transaction.is_active()
                assert handle._att.get_statement_timeout() == timeout
                assert handle._att.get_idle_timeout() == case[
                    'session_idle_timeout_seconds']
                with handle.cursor() as cursor:
                    cursor.execute(
                        "SELECT RDB$GET_CONTEXT('SYSTEM', "
                        "'SESSION_TIMEZONE'), "
                        'TRIM(C.RDB$CHARACTER_SET_NAME) '
                        'FROM MON$ATTACHMENTS A JOIN RDB$CHARACTER_SETS C ON '
                        'C.RDB$CHARACTER_SET_ID = A.MON$CHARACTER_SET_ID '
                        'WHERE A.MON$ATTACHMENT_ID = CURRENT_CONNECTION')
                    assert cursor.fetchone() == (zone, charset)
                    value = 'Grüße 日本' if charset == 'UTF8' else 'Owned text'
                    cursor.execute('SELECT CAST(? AS VARCHAR(40)) '
                                   'FROM RDB$DATABASE', (value,))
                    assert cursor.fetchone() == (value,)
                client.control_transaction(handle, 'rollback')
                assert not handle.main_transaction.is_active()
                result['cases'].append(case)
            except Exception as exc:
                result['failures'].append({
                    **case, 'error_type': type(exc).__name__,
                    'message': str(exc)})
            finally:
                if handle is not None:
                    client.close_session(handle)
    finally:
        client.close()
    result['complete'] = len(result['cases']) == 12 and not result['failures']
    return result


def verify_decimal_options(route):
    result = {'cases': [], 'failures': [], 'complete': False}
    selections = [({'decfloat_round': mode}, 'round', mode)
                  for mode in ('NATIVE_DEFAULT', *MODES)]
    for values in itertools.product((False, True), repeat=len(TRAP_FIELDS)):
        if not any(values):
            continue  # CUSTOM requires at least one native trap.
        fields = dict(zip(TRAP_FIELDS, values))
        expected = sorted(TRAP_FIELDS[key] for key, value in fields.items()
                          if value)
        selections.append(({'decfloat_traps_policy': 'CUSTOM', **fields},
                           'traps', expected))
    client = _create_client(LocalPermissions())
    try:
        for selected, kind, expected in selections:
            handle = None
            try:
                handle = client.open_session({'route': {**route, **selected}})
                observed = (observe_rounding(handle) if kind == 'round'
                            else observe_traps(handle))
                assert observed == (expected_rounding(expected)
                                    if kind == 'round' else expected)
                handle.rollback()
                # RESET must restore the attachment's selected initial state.
                handle.execute_immediate('ALTER SESSION RESET')
                observed_reset = (observe_rounding(handle) if kind == 'round'
                                  else observe_traps(handle))
                assert observed_reset == observed
                handle.rollback()
                result['cases'].append({
                    'selection': selected, 'observed': observed,
                    'reset_preserved_selection': True})
            except Exception as exc:
                result['failures'].append({
                    'selection': selected, 'error_type': type(exc).__name__,
                    'message': str(exc)})
            finally:
                if handle is not None:
                    client.close_session(handle)
    finally:
        client.close()
    result['complete'] = (len(result['cases']) == len(selections) and
                          not result['failures'])
    return result


def verify_role_and_trigger_options(route):
    client = _create_client(LocalPermissions())
    admin = client.open_session({'route': route})
    result = {}
    try:
        with admin.cursor() as cursor:
            cursor.execute('CREATE ROLE OWNED_ROLE')
            cursor.execute('GRANT SELECT ON OWNED_PRIVATE TO OWNED_ROLE')
            cursor.execute('GRANT OWNED_ROLE TO OWNED_ROLE_USER')
        admin.commit()
        handle = client.open_session({'route': {
            **route, 'user': 'OWNED_ROLE_USER', 'role': 'OWNED_ROLE'}})
        try:
            with handle.cursor() as cursor:
                cursor.execute('SELECT CURRENT_USER, CURRENT_ROLE '
                               'FROM RDB$DATABASE')
                assert cursor.fetchone() == ('OWNED_ROLE_USER', 'OWNED_ROLE')
                cursor.execute('SELECT ID FROM OWNED_PRIVATE')
                assert cursor.fetchall() == [(2,)]
            handle.rollback()
            result['explicit_role_and_grant'] = True
        finally:
            client.close_session(handle)
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE EXCEPTION OWNED_CONNECT_DENIED 'Owned gate'")
            cursor.execute('CREATE TRIGGER OWNED_CONNECT_GUARD ACTIVE '
                           'ON CONNECT AS BEGIN '
                           'EXCEPTION OWNED_CONNECT_DENIED; END')
        admin.commit()
        try:
            unexpected = client.open_session({'route': route})
        except RelationalClientError:
            result['connect_trigger_enforced'] = True
        else:
            client.close_session(unexpected)
            raise AssertionError('Connect trigger did not run')
        handle = client.open_session({'route': {
            **route, 'no_db_triggers': True}})
        try:
            with handle.cursor() as cursor:
                cursor.execute('SELECT ID FROM OWNED_PRIVATE')
                assert cursor.fetchall() == [(2,)]
            handle.rollback()
            result['authorized_trigger_suppression'] = True
        finally:
            client.close_session(handle)
    finally:
        # Keep this admitted owner handle alive so cleanup never needs to
        # bypass a trigger merely to repair the disposable fixture.
        try:
            if admin.main_transaction.is_active():
                admin.rollback()
            with admin.cursor() as cursor:
                cursor.execute('SELECT RDB$TRIGGER_NAME FROM RDB$TRIGGERS '
                               "WHERE RDB$TRIGGER_NAME = "
                               "'OWNED_CONNECT_GUARD'")
                if cursor.fetchone():
                    cursor.execute('DROP TRIGGER OWNED_CONNECT_GUARD')
            admin.commit()
        finally:
            client.close_session(admin)
            client.close()
    return result


def verify_runtime_preferences(route):
    result = {'cases': [], 'failures': [], 'complete': False}
    client = _create_client(LocalPermissions())
    try:
        for no_gc, scope, linger in itertools.product(
                (False, True), ('TRANSACTION', 'ATTACHMENT'),
                ('NATIVE_DEFAULT', 'SUPPRESS')):
            selected = {'no_gc': no_gc, 'dbkey_scope': scope,
                        'no_linger': linger,
                        'attachment_cache_policy': 'CUSTOM',
                        'attachment_cache_pages': 128,
                        'parallel_workers_policy': 'CUSTOM',
                        'parallel_workers': 1}
            handle = None
            try:
                handle = client.open_session({'route': {**route, **selected}})
                core = client.module.core

                def parameter(tag, default=0):
                    # Driver 1.10.11 DPB.parse_buffer never advances its
                    # iterator. Use bounded native tag lookup instead.
                    with core.a.get_api().util.get_xpb_builder(
                            core.XpbKind.DPB, handle._dpb) as buffer:
                        return (buffer.get_int() if buffer.find_first(tag)
                                else default)

                assert bool(parameter(
                    core.DPBItem.NO_GARBAGE_COLLECT)) == no_gc
                assert core.DBKeyScope(parameter(
                    core.DPBItem.DBKEY_SCOPE)).name == scope
                assert bool(parameter(core.DPBItem.NOLINGER)) == (
                    linger == 'SUPPRESS')
                assert parameter(core.DPBItem.NUM_BUFFERS) == 128
                assert parameter(core.DPBItem.PARALLEL_WORKERS) == 1
                with handle.cursor() as cursor:
                    cursor.execute('SELECT MON$GARBAGE_COLLECTION FROM '
                                   'MON$ATTACHMENTS WHERE '
                                   'MON$ATTACHMENT_ID = CURRENT_CONNECTION')
                    assert bool(cursor.fetchone()[0]) == (not no_gc)
                    cursor.execute("SELECT RDB$GET_CONTEXT('SYSTEM', "
                                   "'PARALLEL_WORKERS') FROM RDB$DATABASE")
                    workers = int(cursor.fetchone()[0])
                    cursor.execute('SELECT RDB$CONFIG_VALUE FROM RDB$CONFIG '
                                   "WHERE RDB$CONFIG_NAME = "
                                   "'MaxParallelWorkers'")
                    cap = int(cursor.fetchone()[0])
                    assert workers == min(1, cap)
                pages = handle.info.page_cache_size
                assert pages > 0
                handle.rollback()
                result['cases'].append({
                    'selection': selected, 'native_dpb_verified': True,
                    'observed_cache_pages': pages,
                    'observed_parallel_workers': workers})
            except Exception as exc:
                result['failures'].append({
                    'selection': selected, 'error_type': type(exc).__name__,
                    'message': str(exc)})
            finally:
                if handle is not None:
                    client.close_session(handle)
    finally:
        client.close()
    result['complete'] = len(result['cases']) == 8 and not result['failures']
    return result


def run(root):
    results = {}
    with tempfile.TemporaryDirectory(
            prefix='owned-embedded-', dir=root) as tmp:
        path = str(Path(tmp) / 'owned.fdb')
        route = {'attachment_mode': 'embedded', 'database': path,
                 'filesystem_root': tmp, 'user': 'SYSDBA'}
        client = _create_client(LocalPermissions())
        connection = None
        try:
            if os.name == 'posix' and os.geteuid() != 0:
                denied = Path(tmp) / 'no-write'
                denied.mkdir(mode=0o500)
                denied_file = str(denied / 'denied.fdb')
                try:
                    arguments = client.config.database_create_arguments(
                        route, denied_file, {})
                    try:
                        unexpected = client.config.database_creator(
                            **arguments)
                    except client.module.DatabaseError:
                        assert not Path(denied_file).exists()
                        results['os_creation_permission_enforced'] = True
                    else:
                        unexpected.drop_database()
                        raise AssertionError('OS write restriction bypassed')
                finally:
                    denied.chmod(0o700)
            else:
                raise RuntimeError(
                    'This permission gate requires an unprivileged POSIX user')
            args = client.config.database_create_arguments(route, path, {})
            connection = client.config.database_creator(**args)
            cursor = connection.cursor()
            cursor.execute('CREATE TABLE OWNED_PRIVATE (ID INTEGER)')
            cursor.execute('CREATE TABLE OWNED_FLAGS (ID INTEGER)')
            connection.commit()
            cursor.execute('INSERT INTO OWNED_PRIVATE VALUES (1)')
            connection.rollback()
            cursor.execute('SELECT COUNT(*) FROM OWNED_PRIVATE')
            assert cursor.fetchone() == (0,)
            cursor.execute('INSERT INTO OWNED_PRIVATE VALUES (2)')
            cursor.execute('GRANT SELECT ON OWNED_PRIVATE TO OWNED_READ_ONLY')
            connection.commit()
            connection.close()
            connection = None
            results['create_commit_rollback'] = True
            transaction_result = verify_route(route, LocalPermissions())
            (root / 'transaction-options.json').write_text(
                json.dumps(transaction_result, indent=2) + '\n')
            assert transaction_result['complete'], transaction_result
            results['native_transaction_option_cases'] = len(
                transaction_result['cases'])
            flag_result = verify_transaction_flags(route)
            (root / 'transaction-flags.json').write_text(
                json.dumps(flag_result, indent=2) + '\n')
            assert flag_result['complete'], flag_result
            results['native_transaction_flag_cases'] = len(
                flag_result['cases'])
            limbo_result = verify_limbo(route)
            (root / 'limbo.json').write_text(
                json.dumps(limbo_result, indent=2) + '\n')
            assert limbo_result['complete'], limbo_result
            results['native_limbo_and_recovery'] = True
            session_result = verify_session_options(route)
            (root / 'session-options.json').write_text(
                json.dumps(session_result, indent=2) + '\n')
            assert session_result['complete'], session_result
            results['native_session_option_cases'] = len(
                session_result['cases'])
            decimal_result = verify_decimal_options(route)
            (root / 'decimal-options.json').write_text(
                json.dumps(decimal_result, indent=2) + '\n')
            assert decimal_result['complete'], decimal_result
            results['native_decimal_option_cases'] = len(
                decimal_result['cases'])
            results['native_role_and_trigger_options'] = (
                verify_role_and_trigger_options(route))
            runtime_result = verify_runtime_preferences(route)
            (root / 'runtime-preferences.json').write_text(
                json.dumps(runtime_result, indent=2) + '\n')
            assert runtime_result['complete'], runtime_result
            results['native_runtime_preference_cases'] = len(
                runtime_result['cases'])
            verify_file_failures(client, route)
            results['unreadable_missing_malformed_files_refused'] = True
            results['failed_attachment_retry_same_client'] = True
            for _round in range(3):
                verify_concurrent_identities(route)
            results['concurrent_sql_identities_and_grants_isolated'] = True
            results['concurrent_identity_rounds'] = 3
            connection = client.open_session({'route': route})
            cursor = connection.cursor()
            cursor.execute(
                'REVOKE SELECT ON OWNED_PRIVATE FROM OWNED_READ_ONLY')
            connection.commit()
            client.close_session(connection)
            connection = None
            connection = client.open_session({'route': {
                **route, 'user': 'OWNED_READ_ONLY'}})
            cursor = connection.cursor()
            try:
                cursor.execute('SELECT ID FROM OWNED_PRIVATE')
            except client.module.DatabaseError:
                results['revoked_grant_enforced_on_reattach'] = True
            else:
                raise AssertionError('Reattachment retained revoked grant')
            connection.rollback()
            client.close_session(connection)
            connection = None
            verify_provider(route)
            results['provider_discovery_and_session_without_network'] = True
            results['provider_transport_switch_refused'] = True
            connection = client.open_session({'route': route})
            cursor = connection.cursor()
            cursor.execute(
                "SELECT RDB$GET_CONTEXT('SYSTEM', 'ENGINE_VERSION'), "
                'MON$REMOTE_PROTOCOL FROM MON$ATTACHMENTS '
                'WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')
            version, protocol = cursor.fetchone()
            assert version == '5.0.4' and protocol is None
            cursor.execute('SELECT ID FROM OWNED_PRIVATE')
            assert cursor.fetchone() == (2,)
            connection.rollback()
            client.close_session(connection)
            connection = None
            results['production_attach_engine13_only'] = True
            connection = client.open_session({'route': {
                **route, 'user': 'OWNED_EMBEDDED_READER'}})
            cursor = connection.cursor()
            cursor.execute('SELECT CURRENT_USER FROM RDB$DATABASE')
            assert cursor.fetchone()[0].strip() == 'OWNED_EMBEDDED_READER'
            try:
                cursor.execute('SELECT ID FROM OWNED_PRIVATE')
            except client.module.DatabaseError:
                results['sql_privileges_enforced_without_password'] = True
            else:
                raise AssertionError('Embedded user bypassed SQL privileges')
            connection.rollback()
            client.close_session(connection)
            connection = None
            try:
                client.runtime_identity({'route': {
                    **route, 'database': None}})
            except RelationalClientError:
                results['server_scope_refused'] = True
            else:
                raise AssertionError('Embedded server scope was accepted')
            connection = client.open_session({'route': route})
            connection.drop_database()
            client.close_session(connection)
            connection = None
            assert not Path(path).exists()
            results['drop'] = True
        finally:
            if connection is not None and not connection.is_closed():
                connection.close()
            client.close()
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', required=True, type=Path)
    args = parser.parse_args()
    args.evidence_root.mkdir(parents=True, exist_ok=False)
    outcome = run(args.evidence_root)
    (args.evidence_root / 'result.json').write_text(
        json.dumps(outcome, indent=2) + '\n')
