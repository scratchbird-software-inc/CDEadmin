"""Variadic names must not become fixed ABI arguments on ARM64."""
import ctypes
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.event_abi import install


def test_fixed_event_signature_survives_different_collector_sizes():
    native = Mock(return_value=42)
    fixed = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort)
    api = SimpleNamespace(client_library=SimpleNamespace(isc_event_block=native),
                          P_isc_event_block_args=fixed)
    install(api)
    assert api.isc_event_block(None, None, b'first') == 42
    assert api.isc_event_block(None, None, b'first', b'second') == 42
    assert native.argtypes == list(fixed)
    assert native.restype == ctypes.c_int32
    assert native.call_args.args[:3] == (None, None, 2)
    assert [item.value for item in native.call_args.args[3:]] == [b'first', b'second']
    selected = api.isc_event_block
    install(api)
    assert api.isc_event_block is selected
    for names in ((), (b'name',)*16):
        with pytest.raises(ValueError):
            api.isc_event_block(None, None, *names)
