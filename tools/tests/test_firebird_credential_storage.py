"""FM-FB02-005 fault injection: these are not native server failures."""

from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.endpoints.credential_storage import (
    encrypted_credentials, protected_configuration_write,
)
from pgadmin.cdeadmin.endpoints.profiles import EndpointRegistrationError


@pytest.mark.parametrize('failure', [
    'policy', 'locked', 'key', 'cipher', None,
])
def test_encryption_boundary(monkeypatch, failure):
    secret = 'owned secret with spaces 密'
    encrypt = Mock(return_value='ciphertext')
    key = Mock(return_value=(failure != 'locked', 'key'))
    if failure == 'key':
        key.side_effect = RuntimeError(secret)
    if failure == 'cipher':
        encrypt.side_effect = RuntimeError(secret)
    monkeypatch.setitem(sys.modules, 'config', SimpleNamespace(
        ALLOW_SAVE_PASSWORD=failure != 'policy'))
    monkeypatch.setitem(sys.modules, 'pgadmin.utils.crypto',
                        SimpleNamespace(encrypt=encrypt))
    monkeypatch.setitem(sys.modules, 'pgadmin.utils.master_password',
                        SimpleNamespace(get_crypt_key=key))
    if failure:
        with pytest.raises(EndpointRegistrationError) as captured:
            encrypted_credentials(secret)
        assert secret not in str(captured.value)
        if failure in ('policy', 'locked', 'key'):
            encrypt.assert_not_called()
    else:
        assert encrypted_credentials(secret) == 'ciphertext'
        encrypt.assert_called_once_with(secret, 'key')


@pytest.mark.parametrize('rollback_fails', [False, True])
def test_sql_failure_and_rollback_never_expose_bind_values(rollback_fails):
    session = Mock()
    if rollback_fails:
        session.rollback.side_effect = RuntimeError('secret rollback bind')
    with pytest.raises(EndpointRegistrationError) as captured:
        with protected_configuration_write(session):
            raise RuntimeError('secret SQL bind')
    assert str(captured.value) == 'endpoint configuration could not be saved'
    assert captured.value.__suppress_context__
    session.rollback.assert_called_once_with()


def test_success_does_not_rollback():
    session = Mock()
    with protected_configuration_write(session):
        session.commit()
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_concurrent_transient_credentials_are_isolated_and_zeroed():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from pgadmin.cdeadmin.endpoints.service import ProtectedColumnResolver
    resolver = ProtectedColumnResolver()
    entered, release = Event(), Event()
    buffers = []

    def owner():
        with resolver.transient('server:1:password', 'first'):
            buffers.append(resolver._transient['server:1:password'])
            entered.set()
            assert release.wait(10)
            assert bytes(buffers[0]) == b'first'

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(owner)
        try:
            assert entered.wait(10)
            with pytest.raises(EndpointRegistrationError,
                               match='already in use'):
                with resolver.transient('server:1:password', 'replacement'):
                    pytest.fail('overlapping credential admitted')
            with resolver.transient('server:2:password', 'second'):
                buffers.append(resolver._transient['server:2:password'])
                assert bytes(buffers[1]) == b'second'
        finally:
            release.set()
        future.result()
    assert resolver._transient == {}
    assert all(not any(buffer) for buffer in buffers)


@pytest.mark.parametrize('operation', ['verify', 'edit'])
def test_service_failure_cleans_up_without_exposing_secret(
        monkeypatch, operation):
    from pgadmin.cdeadmin.endpoints.service import EndpointService
    service = EndpointService(SimpleNamespace(), SimpleNamespace(
        secrets=SimpleNamespace(register_resolver=Mock())))
    session = Mock()
    monkeypatch.setitem(sys.modules, 'pgadmin.model', SimpleNamespace(
        db=SimpleNamespace(session=session)))
    service.forget_server_credentials = Mock()
    server = SimpleNamespace(endpoint_profile=None)
    if operation == 'verify':
        service._verify_server = Mock(side_effect=RuntimeError('secret bind'))

        def call():
            return service.verify_server(server, 'secret bind')
    else:
        service._update_endpoint_profile = Mock(
            side_effect=RuntimeError('secret bind'))

        def call():
            return service.update_endpoint_profile(server, {})
    with pytest.raises(EndpointRegistrationError) as captured:
        call()
    assert 'secret bind' not in str(captured.value)
    assert captured.value.__suppress_context__
    session.rollback.assert_called_once_with()
    service.forget_server_credentials.assert_called_once_with(server)


def test_real_cipher_unicode_roundtrip_and_randomized_storage():
    import importlib.util
    from pathlib import Path
    source = Path(__file__).resolve().parents[2] / (
        'web/pgadmin/utils/crypto.py')
    spec = importlib.util.spec_from_file_location('owned_crypto_test', source)
    crypto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crypto)
    secret = 'owned unicode 密 password with spaces'
    first = crypto.encrypt(secret, 'owned-key')
    second = crypto.encrypt(secret, 'owned-key')
    assert first != second
    assert secret.encode() not in first
    assert crypto.decrypt(first, 'owned-key').decode() == secret
    assert crypto.decrypt(second, 'owned-key').decode() == secret
    assert crypto.decrypt(first, 'wrong-key') != secret.encode()


@pytest.mark.parametrize('failure', [
    'decrypt', 'key', 'locked', 'missing', 'owner', 'endpoint', None,
])
def test_protected_resolver_boundary(monkeypatch, failure):
    from pgadmin.cdeadmin.endpoints.service import ProtectedColumnResolver
    resolver = ProtectedColumnResolver()
    source = SimpleNamespace(user_id=7, password=(
        None if failure == 'missing' else 'cipher'),
        endpoint_profile=SimpleNamespace(id='owned'))
    query = Mock()
    query.filter_by.return_value.first.return_value = source
    monkeypatch.setitem(sys.modules, 'pgadmin.model', SimpleNamespace(
        Server=SimpleNamespace(query=query), SharedServer=None))
    monkeypatch.setitem(sys.modules, 'flask_login', SimpleNamespace(
        current_user=SimpleNamespace(is_authenticated=True, id=7)))
    decrypt = Mock(return_value=b'owned-secret')
    key = Mock(return_value=(failure != 'locked', 'key'))
    if failure == 'decrypt':
        decrypt.side_effect = RuntimeError('owned-secret')
    if failure == 'key':
        key.side_effect = RuntimeError('owned-secret')
    monkeypatch.setitem(sys.modules, 'pgadmin.utils.crypto',
                        SimpleNamespace(decrypt=decrypt))
    monkeypatch.setitem(sys.modules, 'pgadmin.utils.master_password',
                        SimpleNamespace(get_crypt_key=key))
    context = SimpleNamespace(endpoint_id=(
        'other' if failure == 'endpoint' else 'owned'))
    principal = 'user:8' if failure == 'owner' else 'user:7'
    if failure:
        with pytest.raises(EndpointRegistrationError) as captured:
            resolver('server:1:password', context, 'verify', principal)
        assert str(captured.value) == (
            'protected endpoint credential is unavailable')
        if failure in ('owner', 'endpoint', 'locked', 'missing', 'key'):
            decrypt.assert_not_called()
    else:
        assert resolver('server:1:password', context, 'verify', principal) == (
            b'owned-secret')


@pytest.mark.parametrize('mode', [
    'save', 'no-save', 'string-false', 'string-true', 'invalid', 'alternate',
    'locked', 'policy', 'cipher', 'commit', 'auth', 'non-owner',
])
def test_http_verification_storage_boundary(monkeypatch, mode):
    # Execute the actual route body with only framework dependencies replaced.
    # Real Flask/browser/native paths are covered separately by the live gate.
    import ast
    import json
    from pathlib import Path
    source = Path(__file__).resolve().parents[2] / (
        'web/pgadmin/browser/server_groups/servers/__init__.py')
    function = next(node for node in ast.walk(ast.parse(source.read_text()))
                    if isinstance(node, ast.FunctionDef)
                    and node.name == 'verify_endpoint')
    function.decorator_list = []
    module = ast.Module(body=[function], type_ignores=[])
    session = Mock()
    server = SimpleNamespace(password='old-cipher', save_password=0)
    service = Mock()
    service.verify_server.return_value = {'connected_as': 'default'}
    secret = 'owned-secret 密'
    payload = {'password': secret, 'save_password': True}
    if mode == 'no-save':
        payload['save_password'] = False
    if mode in ('string-false', 'string-true'):
        payload['save_password'] = mode.split('-')[1]
    if mode == 'invalid':
        payload['save_password'] = 'yes'
    if mode == 'alternate':
        payload['connect_as'] = 'other'
    if mode == 'auth':
        service.verify_server.side_effect = EndpointRegistrationError(
            'endpoint verification failed')
    if mode == 'commit':
        session.commit.side_effect = RuntimeError(secret)
    encrypt = Mock(return_value=b'encrypted-only')
    if mode == 'cipher':
        encrypt.side_effect = RuntimeError(secret)
    monkeypatch.setitem(sys.modules, 'config', SimpleNamespace(
        ALLOW_SAVE_PASSWORD=mode != 'policy'))
    monkeypatch.setitem(sys.modules, 'pgadmin.utils.crypto',
                        SimpleNamespace(encrypt=encrypt))
    monkeypatch.setitem(sys.modules, 'pgadmin.utils.master_password',
                        SimpleNamespace(get_crypt_key=lambda: (
                            mode != 'locked', 'owned-key')))
    scope = {
        'get_server': lambda sid: server,
        '_is_non_owner': lambda server: mode == 'non-owner',
        '_cde_registration': lambda server: {
            'workflow': 'provider_endpoint', 'available': True},
        'request': SimpleNamespace(form={}, data=json.dumps(payload)),
        'json': json, 'gettext': lambda text: text,
        'bad_request': lambda text: {'status': 400, 'errormsg': text},
        'forbidden': lambda **kw: {'status': 403, **kw},
        'make_json_response': lambda **kw: kw,
        'endpoint_service_for_app': lambda app: service,
        'current_app': None, 'db': SimpleNamespace(session=session),
        'EndpointRegistrationError': EndpointRegistrationError,
        'server_icon_and_background': lambda *args: 'connected',
    }
    exec(compile(module, str(source), 'exec'), scope)
    result = scope['verify_endpoint'](SimpleNamespace(), 1, 1)
    assert secret not in str(result)
    saved = mode in ('save', 'string-true')
    if saved:
        assert server.password == b'encrypted-only'
        assert server.save_password == 1
        session.commit.assert_called_once_with()
    elif mode != 'commit':
        session.commit.assert_not_called()
        assert server.password == 'old-cipher'
    if mode in ('policy', 'locked', 'cipher', 'alternate',
                'invalid', 'non-owner'):
        service.verify_server.assert_not_called()
    if mode == 'commit':
        session.rollback.assert_called_once_with()
        service.forget_server_credentials.assert_called_once_with(server)
    if mode in ('no-save', 'string-false'):
        encrypt.assert_not_called()
        assert result['data']['is_password_saved'] is False
