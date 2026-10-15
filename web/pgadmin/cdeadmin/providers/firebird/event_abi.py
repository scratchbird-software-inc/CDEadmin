"""Bind native event varargs with the ABI's three fixed parameters.

Driver 1.10.11 converts event names to fixed CFUNCTYPE parameters. Apple
Silicon passes actual variadic arguments differently. A CDLL function with
only the three fixed argtypes lets ctypes/libffi use the platform varargs ABI.
The signature also stays fixed when concurrent collectors have different sizes.
"""
import ctypes
import sys
import threading

_LOCK = threading.Lock()


class _OwnedCollector:
    """Release the two native EPB allocations only after confirmed cancellation."""

    def __init__(self, collector, free, cancel=None):
        self._collector = collector
        self._free = free
        self._cancel = cancel
        self._callbacks = []
        self._lock = threading.RLock()
        self.buffers_released = False

    def __getattr__(self, name):
        return getattr(self._collector, name)

    def _retain_callbacks(self):
        for block in self._collector._EventCollector__event_blocks:
            callback = getattr(block, '_EventBlock__callback', None)
            if callback is not None and callback not in self._callbacks:
                self._callbacks.append(callback)

    def begin(self):
        try:
            return self._collector.begin()
        finally:
            self._retain_callbacks()

    def close(self):
        with self._lock:
            if self.buffers_released:
                return
            self._retain_callbacks()
            self._collector.close()
            # The pinned collector joins its processing thread and cancels
            # each event block before returning. A failed cancellation raises
            # above, retaining allocations and callbacks for the owned retry.
            for block in self._collector._EventCollector__event_blocks:
                if not block.is_closed():
                    raise RuntimeError('Native event cancellation incomplete')
                status = getattr(block, '_isc_status', None)
                if status is not None and status[0] == 1 and status[1]:
                    # Driver 1.10.11 marks blocks closed even when cancellation
                    # failed. A later no-op close is not cancellation proof.
                    if self._cancel is None:
                        raise RuntimeError('Native event cancellation unconfirmed')
                    self._cancel(block)
                for name in ('event_buf', 'result_buf'):
                    buffer = getattr(block, name)
                    if buffer:
                        self._free(ctypes.cast(buffer, ctypes.c_void_p))
                        setattr(block, name, ctypes.POINTER(ctypes.c_ubyte)())
            self.buffers_released = True
            self._callbacks.clear()


def event_collector(connection, names):
    from firebird.driver.core import Connection
    if isinstance(connection, Connection):
        from firebird.driver import get_api
        api = get_api()
        install(api)
        free = api.client_library.isc_free
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_int32
        from firebird.driver import fbapi

        def cancel(block):
            status = fbapi.ISC_STATUS_ARRAY()
            api.isc_cancel_events(status, block._db_handle, block.event_id)
            if fbapi.db_api_error(status) and status[1] != 335544324:
                from firebird.driver import DatabaseError
                raise fbapi.exception_from_status(DatabaseError, status,
                                                  'Native event cancellation unconfirmed')
            # Firebird 5 destroys child events before removing the attachment's
            # handle mapping. isc_bad_db_handle thus also confirms teardown.

        collector = connection.event_collector(names)
        owner = _OwnedCollector(collector, free, cancel)
        # Connection.close/drop owns these collectors too. Retain the wrapper
        # there so retry and teardown follow the same allocation ownership.
        registered = connection._Connection__ecollectors
        registered[registered.index(collector)] = owner
        return owner
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
        fixed = list(api.P_isc_event_block_args)
        if len(fixed) != 3:
            raise ValueError('Unexpected native event block ABI')
        if sys.platform == 'darwin':
            # Apple's libffi checks fixed arguments after the first one as
            # though they were variadic, refusing Firebird's uint16 count.
            # Values 1..15 have the same zero-extended register representation
            # as uint32 on both admitted 64-bit Mac ABIs. Keep all three fixed
            # arguments so ARM64 event-name pointers still use variadic slots.
            fixed[2] = ctypes.c_uint32
        # ctypes caches converters when assigning this property. Mutating an
        # already assigned list leaves the old uint16 converter active.
        native.argtypes = fixed

        def event_block(event_buffer, result_buffer, *names):
            if not 1 <= len(names) <= 15:
                raise ValueError('Native event block requires 1–15 names')
            return native(event_buffer, result_buffer, len(names),
                          *(ctypes.c_char_p(name) for name in names))

        api.isc_event_block = event_block
        api._cdeadmin_variadic_events = True
