"""Bind native event varargs with the ABI's three fixed parameters.

Driver 1.10.11 converts event names to fixed CFUNCTYPE parameters. Apple
Silicon passes actual variadic arguments differently. A CDLL function with
only the three fixed argtypes lets ctypes/libffi use the platform varargs ABI.
The signature also stays fixed when concurrent collectors have different sizes.
"""
import ctypes
import threading

_LOCK = threading.Lock()


def event_collector(connection, names):
    from firebird.driver.core import Connection
    if isinstance(connection, Connection):
        from firebird.driver import get_api
        install(get_api())
    return connection.event_collector(names)


def install(api):
    with _LOCK:
        if getattr(api, '_cdeadmin_variadic_events', False) is True:
            return
        # firebird-driver loads WinDLL for the fixed stdcall API. The event
        # builder is explicitly cdecl/variadic, including on Windows. Reuse
        # the admitted library's handle through a cdecl view of that library.
        library = ctypes.CDLL(str(api.client_library_name), handle=api.client_library._handle)
        native = library.isc_event_block
        native.restype = ctypes.c_int32
        native.argtypes = list(api.P_isc_event_block_args)
        if len(native.argtypes) != 3:
            raise ValueError('Unexpected native event block ABI')

        def event_block(event_buffer, result_buffer, *names):
            if not 1 <= len(names) <= 15:
                raise ValueError('Native event block requires 1–15 names')
            return native(event_buffer, result_buffer, len(names),
                          *(ctypes.c_char_p(name) for name in names))

        api.isc_event_block = event_block
        api._cdeadmin_variadic_events = True
