#!/usr/bin/env python3
"""Portable native driver checks in one uniquely owned disposable database.

Run in a fresh Python process on Windows, macOS or Linux. This runner uses an
already installed runtime/server; it never stages Linux libraries or starts a
server. The route must not name an existing database or hold passwords.
Only the database successfully created by this invocation is dropped.
"""
import argparse
import base64
import getpass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import traceback
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.provider import (
    _create_client, _database_create_arguments, _client_library_identity,
)
from pgadmin.cdeadmin.providers.firebird.connection_strings import database_dsn
from pgadmin.cdeadmin.security.secrets import SecretLease


def run(route, directory, evidence, *, password=None, path_style='posix',
        exhaustive_codecs=False):
    """Return a redacted receipt; retain independent failures and cleanup."""
    import firebird.driver as native

    if not isinstance(route, dict) or any(key in route for key in (
            'database', 'password', 'credential_reference_id',
            'principal_reference')):
        raise ValueError('Use a route without a database or credential fields')
    if route.get('charset', 'UTF8') != 'UTF8':
        raise ValueError('The platform baseline uses UTF8 attachments')
    embedded = route.get('attachment_mode') == 'embedded'
    if (not embedded and not route.get('host') and
            route.get('protocol') != 'XNET'):
        raise ValueError('Network mode requires an explicit host or XNET')
    if path_style not in {'posix', 'windows'}:
        raise ValueError('Invalid server path style')
    path_type = PureWindowsPath if path_style == 'windows' else PurePosixPath
    parent = path_type(directory)
    if not parent.is_absolute() or str(parent) == parent.anchor:
        raise ValueError('Use an absolute dedicated test directory')
    identity = 'scratchrobin_driver_' + uuid.uuid4().hex + '.fdb'
    target = dict(route, database=str(parent / identity), charset='UTF8')
    if embedded:
        if password is not None:
            raise ValueError('Embedded mode does not use a password')
        target['filesystem_root'] = str(parent)
    else:
        target.update(credential_reference_id='owned-platform-secret',
                      principal_reference='owned-platform-principal')
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parents[1]
    package = source / 'web/pgadmin/cdeadmin/providers/firebird'
    receipt = {
        'schema': 'cdeadmin.firebird-driver-platform-proof.v1',
        'complete': False, 'platform': platform.platform(),
        'machine': platform.machine(), 'python': platform.python_version(),
        'driver_version': importlib.metadata.version('firebird-driver'),
        'attachment_mode': 'embedded' if embedded else 'network',
        'checks': [], 'failures': [], 'fixture_created': False,
        'fixture_removed': False, 'handles_released': False,
        'fixture_name': identity,
        'runner_sha256': hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        'source_sha256': {p.relative_to(source).as_posix(): hashlib.sha256(
            p.read_bytes()).hexdigest() for p in sorted(package.iterdir())
            if p.suffix in {'.py', '.json'}},
    }
    owner = observer = client = None

    def failed(stage, error):
        receipt['failures'].append({
            'stage': stage, 'type': type(error).__name__,
            'locations': [{'file': Path(frame.filename).name,
                           'line': frame.lineno}
                          for frame in traceback.extract_tb(
                              error.__traceback__)]})

    try:
        permissions = SimpleNamespace(
            require=lambda *_args: None,
            acquire_secret=lambda *_args: SecretLease(password))
        if embedded:
            from pgadmin.cdeadmin.providers.firebird.embedded_provider import PROFILE, ADMINISTRATION
            client = _create_client(permissions, attachment_mode='embedded',
                                    profile=PROFILE, administration=ADMINISTRATION)
        else:
            client = _create_client(permissions, attachment_mode='network')
        destination = database_dsn(target['database'], target.get('host'),
                                   target.get('port'), target.get('protocol'))
        args = _database_create_arguments(
            target, destination, {'default_charset': 'UTF8'}, native)
        owner = client.config.database_creator(password=password, **args)
        client._connections.append(owner)
        receipt['fixture_created'] = True
        receipt.update(_client_library_identity(native))
        library = os.environ.get('CDEADMIN_FIREBIRD_CLIENT_LIBRARY')
        if library and Path(library).is_file():
            receipt['client_library_sha256'] = hashlib.sha256(
                Path(library).read_bytes()).hexdigest()

        def sql(handle, text, parameters=()):
            result = client.describe_result(client.execute(handle, {
                'source': text, 'parameters': list(parameters)}))
            return result['payload'].get('rows', [])

        version = sql(owner, "SELECT RDB$GET_CONTEXT('SYSTEM', "
                      "'ENGINE_VERSION') FROM RDB$DATABASE")[0][0]
        receipt['engine_version'] = version
        assert version == '5.0.4'
        protocol = sql(owner, 'SELECT MON$REMOTE_PROTOCOL FROM MON$ATTACHMENTS '
                       'WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')[0][0]
        receipt['remote_protocol'] = protocol
        receipt['auth_method'] = sql(owner, 'SELECT MON$AUTH_METHOD FROM MON$ATTACHMENTS '
                                    'WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')[0][0]
        assert (protocol is None) if embedded else bool(protocol)
        if route.get('protocol') == 'XNET':
            assert protocol == 'XNET', protocol
        if route.get('trusted_auth'):
            receipt['authenticated_user'] = sql(owner, 'SELECT CURRENT_USER FROM RDB$DATABASE')[0][0]
            assert receipt['authenticated_user'] == 'SYSDBA'
            assert receipt['auth_method'] == 'Win_Sspi'
        sql(owner, 'CREATE TABLE OWNED_DRIVER(ID INT PRIMARY KEY, '
            '"été" VARCHAR(80) CHARACTER SET UTF8, '
            'A INTEGER[-1:1], TXT BLOB SUB_TYPE TEXT CHARACTER SET UTF8)')
        client.control_transaction(owner, 'commit')
        observer = client.open_session({'route': target})
        receipt['checks'].append('provider_create_and_independent_open')
        text = 'é日本🙂' * 20000
        sql(owner, 'INSERT INTO OWNED_DRIVER VALUES(?,?,?,?)',
            [1, 'été日本', [10, 20, 30], text])
        row = sql(owner, 'SELECT "été", A, TXT FROM OWNED_DRIVER')[0]
        assert row == ('été日本', [10, 20, 30], text)
        assert sql(observer, 'SELECT COUNT(*) FROM OWNED_DRIVER') == [(0,)]
        client.control_transaction(observer, 'rollback')
        receipt['checks'].append(
            'metadata_scalar_array_blob_pending_visibility')
        client.control_transaction(owner, 'rollback')
        assert sql(owner, 'SELECT COUNT(*) FROM OWNED_DRIVER') == [(0,)]
        sql(owner, 'INSERT INTO OWNED_DRIVER VALUES(?,?,?,?)',
            [2, 'été日本', [30, 20, 10], text])
        client.control_transaction(owner, 'commit')
        assert sql(observer, 'SELECT COUNT(*) FROM OWNED_DRIVER') == [(1,)]
        client.control_transaction(observer, 'rollback')
        receipt['checks'].append('rollback_and_committed_visibility')

        def stream(action, **values):
            return client.query_stream(owner, {
                'stream_action': action, 'owner_id': 'platform-gate',
                **values})

        page = stream('open', source='SELECT TXT FROM OWNED_DRIVER')
        reference = page['rows'][0][0]['blob_reference']
        raw = bytearray()
        try:
            while True:
                part = stream(
                    'blob', stream_reference=page['stream_reference'],
                    blob_reference=reference, offset=len(raw))
                raw.extend(base64.b64decode(part['data']))
                if part['complete']:
                    break
            assert raw.decode(owner._encoding) == text
        finally:
            stream('close')
        receipt['checks'].append('bounded_blob_stream')
        if exhaustive_codecs:
            from tools.cdeadmin_firebird_legacy_codec_oracle_gate import (
                qualify as legacy_codecs,
            )
            from tools.cdeadmin_firebird_gb18030_oracle_gate import (
                qualify as gb18030,
            )
            for name, check in (('legacy-codecs', legacy_codecs),
                                ('gb18030-codec', gb18030)):
                destination = evidence / name
                destination.mkdir()
                check(native, owner, target, None, destination, None)
                receipt['checks'].append(name)
            from tools.cdeadmin_firebird_fss_gate import conversion_oracle
            destination = evidence / 'unicode-fss-codec'
            destination.mkdir()
            conversion_oracle(owner, destination)
            receipt['checks'].append('unicode-fss-codec')
            client.control_transaction(owner, 'rollback')
        if not embedded:
            service = client._connect_server({'route': {
                key: value for key, value in target.items()
                if key != 'database'}})
            try:
                assert '5.0.4' in service.info.version
                receipt['checks'].append('native_services_attachment')
            finally:
                client.close_session(service)
    except Exception as error:
        failed('checks', error)
    finally:
        if observer is not None:
            try:
                client.close_session(observer)
            except Exception as error:
                failed('observer_close', error)
        if owner is not None:
            try:
                # Native drop closes transaction managers, active or idle.
                owner.drop_database()
                receipt['fixture_removed'] = True
                client.close_session(owner)
            except Exception as error:
                failed('owned_database_cleanup', error)
        if client is not None:
            try:
                client.close()
                receipt['handles_released'] = not client._connections
            except Exception as error:
                failed('client_close', error)
        receipt['complete'] = bool(
            receipt['fixture_created'] and receipt['fixture_removed'] and
            receipt['handles_released'] and not receipt['failures'])
        (evidence / 'summary.json').write_text(
            json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route-json', type=Path, required=True)
    parser.add_argument('--fixture-directory', required=True)
    parser.add_argument('--server-path-style', choices=['posix', 'windows'],
                        default='windows' if os.name == 'nt' else 'posix')
    parser.add_argument('--client-library', type=Path, required=True)
    parser.add_argument('--password-env')
    parser.add_argument('--exhaustive-codecs', action='store_true')
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    if not options.client_library.is_file():
        parser.error('Client library does not exist')
    os.environ['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = str(
        options.client_library.resolve())
    route = json.loads(options.route_json.read_text(encoding='utf-8'))
    password = None
    if (route.get('attachment_mode') != 'embedded' and
            not route.get('trusted_auth')):
        password = (os.environ[options.password_env] if options.password_env
                    else getpass.getpass('Disposable test server password: '))
    result = run(route, options.fixture_directory, options.evidence,
                 password=password, path_style=options.server_path_style,
                 exhaustive_codecs=options.exhaustive_codecs)
    raise SystemExit(0 if result['complete'] else 1)
