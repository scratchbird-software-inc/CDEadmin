"""Variadic names must not become fixed ABI arguments on ARM64."""
import ctypes
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.event_abi import install, _OwnedCollector


@pytest.mark.parametrize('platform', ['linux', 'win32', 'darwin'])
def test_fixed_event_signature_survives_different_collector_sizes(platform):
    native = Mock(return_value=42)
    fixed = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort)
    api = SimpleNamespace(client_library=SimpleNamespace(_handle=51), client_library_name='/native/fbclient',
                          P_isc_event_block_args=fixed)
    with patch('pgadmin.cdeadmin.providers.firebird.event_abi.ctypes.CDLL',
               return_value=SimpleNamespace(isc_event_block=native)) as library, \
            patch('pgadmin.cdeadmin.providers.firebird.event_abi.sys.platform', platform):
        install(api)
    library.assert_called_once_with('/native/fbclient', handle=51)
    assert api.isc_event_block(None, None, b'first') == 42
    assert api.isc_event_block(None, None, b'first', b'second') == 42
    assert native.argtypes == [*fixed[:2], ctypes.c_uint32 if platform == 'darwin' else fixed[2]]
    assert native.restype == ctypes.c_int32
    assert native.call_args.args[:3] == (None, None, 2)
    assert [item.value for item in native.call_args.args[3:]] == [b'first', b'second']
    selected = api.isc_event_block
    install(api)
    assert api.isc_event_block is selected
    for names in ((), (b'name',)*16):
        with pytest.raises(ValueError):
            api.isc_event_block(None, None, *names)


def test_native_buffers_release_once_after_collector_cancellation():
    blocks = [SimpleNamespace(event_buf=ctypes.pointer(ctypes.c_ubyte(1)),
                              result_buf=ctypes.pointer(ctypes.c_ubyte(1)),
                              is_closed=lambda: True) for _ in range(2)]
    raw = SimpleNamespace(close=Mock(), _EventCollector__event_blocks=blocks)
    free = Mock(side_effect=lambda _: raw.close.assert_called())
    owner = _OwnedCollector(raw, free)
    owner.close()
    owner.close()
    assert owner.buffers_released
    assert free.call_count == 4
    assert all(not block.event_buf and not block.result_buf for block in blocks)


def test_failed_cancellation_retains_buffers_for_owned_retry():
    block = SimpleNamespace(event_buf=ctypes.pointer(ctypes.c_ubyte(1)),
                            result_buf=ctypes.pointer(ctypes.c_ubyte(1)),
                            is_closed=lambda: True)
    raw = SimpleNamespace(close=Mock(side_effect=RuntimeError('cancel failed')),
                          _EventCollector__event_blocks=[block])
    free = Mock()
    owner = _OwnedCollector(raw, free)
    with pytest.raises(RuntimeError):
        owner.close()
    free.assert_not_called()
    assert not owner.buffers_released and block.event_buf and block.result_buf
    raw.close.side_effect = None
    owner.close()
    assert owner.buffers_released and free.call_count == 2


def test_driver_closed_flag_does_not_hide_a_failed_native_cancellation():
    block = SimpleNamespace(event_buf=ctypes.pointer(ctypes.c_ubyte(1)),
                            result_buf=ctypes.pointer(ctypes.c_ubyte(1)),
                            _isc_status=[1, 335544324], is_closed=lambda: True)
    raw = SimpleNamespace(close=Mock(), _EventCollector__event_blocks=[block])
    free = Mock()
    retry = Mock(side_effect=RuntimeError('still uncertain'))
    owner = _OwnedCollector(raw, free, retry)
    with pytest.raises(RuntimeError): owner.close()
    free.assert_not_called()
    assert not owner.buffers_released
    retry.side_effect = None
    owner.close()
    assert retry.call_count == 2 and owner.buffers_released and free.call_count == 2
