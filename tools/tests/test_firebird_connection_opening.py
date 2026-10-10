"""Owned attachment option parity and failure ownership before publication."""
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
import firebird.driver as native
from firebird.driver.config import DriverConfig
from tools.cdeadmin_firebird_admin_mapping_gate import _route_arguments
from pgadmin.cdeadmin.providers.firebird import connection_opening as opening
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.fixture
def fixture(monkeypatch):
    registry = DriverConfig('owned-attach-test')
    module = SimpleNamespace(driver_config=registry, get_api=MagicMock(),
                             NetProtocol=native.NetProtocol)
    args = _route_arguments(
        {'host': '127.0.0.1', 'port': 53050,
         'database': '/owned.fdb', 'user': 'owner'}, module)
    config = registry.get_database(args['database'])

    class Connection:
        def __init__(self, attachment, dsn, buffer, dialect, charset):
            self._att = attachment
            self.args = (dsn, buffer, dialect, charset)

    core = SimpleNamespace(
        Connection=Connection, _connect_helper=native.core._connect_helper,
        get_callbacks=Mock(return_value=[]),
        ConnectionHook=native.core.ConnectionHook)
    builder = Mock(return_value=b'owned-dpb')
    monkeypatch.setattr(opening, 'build', builder)
    failed = Mock()
    dispatcher = module.get_api().master.get_dispatcher().__enter__()
    return module, core, config, args, builder, failed, dispatcher


def test_native_attachment_options_and_hooks_are_retained(fixture):
    module, core, config, args, builder, failed, dispatcher = fixture
    config.parallel_workers.value = 3
    config.cache_size.value = 257
    config.timeout.value = 19
    handle = opening.connect(module, core, failed_owner=failed, **args,
                             password='leased', role='RÔLE',
                             no_gc=True, no_db_triggers=True)
    options = builder.call_args.args[1]
    assert options['password'] == 'leased'
    assert options['role'] == 'RÔLE'
    assert options['parallel_workers'] == 3
    assert options['cache_size'] == 257 and options['timeout'] == 19
    assert options['utf8filename'] is True
    assert options['no_gc'] and options['no_db_triggers']
    dispatcher.attach_database.assert_called_once_with(
        '127.0.0.1/53050:/owned.fdb', b'owned-dpb', 'utf-8')
    assert handle._cdeadmin_attached_pending
    hook = Mock()
    core.get_callbacks.return_value = [hook]
    opening.notify_attached(core, handle)
    opening.notify_attached(core, handle)
    hook.assert_called_once_with(handle)
    failed.assert_not_called()


@pytest.mark.parametrize('failure', ['constructor', 'dispatcher'])
def test_unpublished_native_owner_is_retained_on_failure(fixture, failure):
    module, core, _config, args, _builder, failed, dispatcher = fixture
    if failure == 'constructor':
        core.Connection.__init__ = Mock(
            side_effect=RuntimeError('constructor'))
    else:
        module.get_api().master.get_dispatcher().__exit__.side_effect = (
            RuntimeError('dispatcher'))
    with pytest.raises(RuntimeError):
        opening.connect(module, core, failed_owner=failed, **args)
    failed.assert_called_once()
    assert (failed.call_args.args[0]._att is
            dispatcher.attach_database.return_value)


def test_native_attach_failure_does_not_invent_an_owner(fixture):
    module, core, _config, args, _builder, failed, dispatcher = fixture
    dispatcher.attach_database.side_effect = RuntimeError('attach refused')
    with pytest.raises(RuntimeError):
        opening.connect(module, core, failed_owner=failed, **args)
    failed.assert_not_called()


def test_only_owned_configurations_are_accepted(fixture):
    module, core, _config, _args, _builder, failed, dispatcher = fixture
    with pytest.raises(RelationalClientError):
        opening.connect(module, core, failed_owner=failed,
                        database='external-config')
    dispatcher.attach_database.assert_not_called()
