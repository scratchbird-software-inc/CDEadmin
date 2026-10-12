#!/usr/bin/env python3
"""Qualify retained Ignite drivers against an owned writable namespace."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import uuid
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package
from tools.cdeadmin_ignite_live_verify import _Permissions  # noqa: E402
from pgadmin.cdeadmin.providers.apache_ignite.provider import (  # noqa: E402
    create_provider,
)


def run(route, destination, password):
    destination = Path(destination).resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError('Evidence must be outside repository')
    destination.mkdir(parents=True, exist_ok=False)
    proof = dict(complete=False, cleanup_complete=False,
                 checks=[], failures=[],
                 platform=platform.platform())
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/apache_ignite').glob('*.py'))
    files += [ROOT / 'web/pgadmin/cdeadmin/providers/retained_native.py',
              Path(__file__)]
    proof['source_sha256'] = {str(f.relative_to(ROOT)): hashlib.sha256(
        f.read_bytes()).hexdigest() for f in files}
    route = dict(route, username=route.get('username', 'ignite'),
                 auth_mode='username-password', principal_reference='qa',
                 credential_references={'database_password': 'root'})
    provider = create_provider(SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=str(uuid.uuid4())),
        _Permissions(password))
    client = provider.client
    table = 'CDE_DRIVER_' + uuid.uuid4().hex.upper()
    cache = 'cde_driver_' + uuid.uuid4().hex
    owned_table = owned_cache = False
    try:
        session = provider.open_session({'route': route})
        owner = provider._sessions[session['session_id']].handle
        handle = owner.handle
        proof['runtime'] = client.runtime_identity({'route': route}, owner)
        proof['driver_version'] = client.backend.module.__version__
        if route.get('tls_mode') == 'verify-full':
            assert handle._nodes[0]._socket.cipher()

        def observe(token):
            pages = []
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                value = provider.describe_result(token)
                page = value['extensions']['apache_ignite']['payload']
                pages.append(page)
                if value['complete']:
                    assert not page.get('error'), page.get('error')
                    return pages
            raise AssertionError('Native operation timeout')

        def query(source, parameters=None, target=None):
            if isinstance(source, dict):
                source = json.dumps(source)
            pages = observe(provider.execute(dict(
                target or session, source=source, parameters=parameters)))
            return [row for page in pages for row in page.get('entries', [])]

        owned_table = True
        query(
            'CREATE TABLE ' +
            table +
            '(ID INT PRIMARY KEY,V BIGINT,B BINARY)')
        query('INSERT INTO ' + table + '(ID,V,B) VALUES (?,?,?)', [
            1, {'type': 'integer', 'value': '9007199254740993'},
            {'type': 'binary', 'value': 'AP8='}])
        rows = query('SELECT V,B,V FROM ' + table)
        integer = {'type': 'integer', 'value': '9007199254740993'}
        binary = {'type': 'binary', 'value': 'AP8='}
        assert rows == [{'c0': integer, 'c1': binary, 'c2': integer}]
        pages = observe(provider.execute(dict(
            session, source='SELECT X FROM SYSTEM_RANGE(1,10017)')))
        assert sum(len(p.get('entries', [])) for p in pages) == 10017
        assert max(len(p.get('entries', [])) for p in pages) <= 256
        proof['checks'].append(
            'exact-bindings-duplicate-columns-bounded-pages')
        handle.create_cache({0: cache, 2: 0})
        owned_cache = True
        command = dict(
            operation='put',
            cache=cache,
            key='owned',
            value='first')
        provider.control_transaction(dict(session, action='begin'))
        query(command)
        provider.control_transaction(dict(session, action='rollback'))
        assert handle.get_cache(cache).get('owned') is None
        provider.control_transaction(dict(session, action='begin'))
        query(command)
        attachments = len(client.backend._clients)
        client.list_resources({'route': route})
        assert len(client.backend._clients) == attachments
        provider.control_transaction(dict(session, action='commit'))
        assert handle.get_cache(cache).get('owned') == 'first'
        proof['checks'].append(
            'worker-context-native-decisions-metadata-isolation')
        value = {'type': 'binary-object', 'value': {
            'name': 'OwnedDriverValue', 'schema': {'name': 'String',
                                                   'number': 'LongObject'},
            'fields': {'name': 'Grüße', 'number': integer}}}
        query(dict(command, key='object', value=value))
        assert query(dict(operation='get', cache=cache, key='object'))[0][
            'value'] == value
        proof['checks'].append('native-binary-object-schema-and-exact-fields')
        provider.control_transaction(dict(session, action='begin'))
        query(dict(command, value='committed-reply-lost'))
        transaction = client.backend.transactions[id(handle)]
        original = transaction.commit
        calls = []

        def reply_loss():
            calls.append(True)
            original()
            raise OSError('owned post-acknowledgement reply-loss fixture')
        transaction.commit = reply_loss
        try:
            provider.control_transaction(dict(session, action='commit'))
        except RuntimeError:
            pass
        else:
            raise AssertionError('Lost reply reported success')
        assert calls == [True]
        assert provider.describe_transaction(session)['provider_payload'][
            'outcome_unknown']
        observer = provider.open_session({'route': route})
        assert query(dict(operation='get', cache=cache, key='owned'),
                     target=observer)[0]['value'] == 'committed-reply-lost'
        provider.close_session(session)
        session = observer
        proof['checks'].append('native-commit-post-ack-failure-no-replay')
        token = provider.execute(dict(
            session, source='SELECT X FROM SYSTEM_RANGE(1,10017)'))
        provider.describe_result(token)
        assert provider.cancel(token)['provider_receipt'][
            'cancel_request_accepted']
        observe(token)
        provider.close_session(session)
        proof['checks'].append('local-cancel-quarantine-and-release')
        proof['complete'] = True
    except Exception as exc:
        proof['failures'].append(dict(type=type(exc).__name__, locations=[
            dict(file=Path(f.filename).name, line=f.lineno)
            for f in traceback.extract_tb(exc.__traceback__)]))
    finally:
        try:
            cleanup = client.backend.open_session({'route': route})
            try:
                if owned_table:
                    statement = 'DROP TABLE IF EXISTS ' + table
                    with cleanup.sql(statement) as cursor:
                        list(cursor)
                if owned_cache:
                    cleanup.get_cache(cache).destroy()
            finally:
                client.backend.close_session(cleanup)
            client.close()
            proof['cleanup_complete'] = True
        except Exception as exc:
            proof['complete'] = False
            proof['failures'].append(dict(phase='cleanup',
                                          type=type(exc).__name__))
        (destination / 'summary.json').write_text(
            json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(json.loads(args.route.read_text()), args.evidence,
                 getpass.getpass('Password: '))
    sys.exit(0 if result['complete'] else 1)
