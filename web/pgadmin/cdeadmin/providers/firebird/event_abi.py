"""Bind native event varargs with the ABI's three fixed parameters.

Driver 1.10.11 converts event names to fixed CFUNCTYPE parameters. Apple
Silicon passes actual variadic arguments differently. A CDLL function with
only the three fixed argtypes lets ctypes/libffi use the platform varargs ABI.
The signature also stays fixed when concurrent collectors have different sizes.
"""
import ctypes
import threading

_LOCK = threading.Lock()


def install(api):
    with _LOCK:
        if getattr(api, '_cdeadmin_variadic_events', False) is True:
            return
        native = api.client_library.isc_event_block
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
