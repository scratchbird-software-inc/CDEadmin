"""Owned CI crash diagnostics: native fault module offsets, without memory dumps."""
import ctypes
from ctypes import wintypes
import json


def install():
    class Record(ctypes.Structure):
        _fields_ = [('code', wintypes.DWORD), ('flags', wintypes.DWORD),
                    ('record', ctypes.c_void_p), ('address', ctypes.c_void_p),
                    ('count', wintypes.DWORD), ('information', ctypes.c_size_t * 15)]

    class Pointers(ctypes.Structure):
        _fields_ = [('record', ctypes.POINTER(Record)), ('context', ctypes.c_void_p)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    get_module = kernel.GetModuleHandleExW
    get_module.argtypes = (wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    get_module.restype = wintypes.BOOL
    filename = kernel.GetModuleFileNameW
    filename.argtypes = (ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD)
    filename.restype = wintypes.DWORD
    capture = kernel.RtlCaptureStackBackTrace
    capture.argtypes = (wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
    capture.restype = wintypes.WORD

    def location(address):
        module = ctypes.c_void_p()
        if address and get_module(6, address, ctypes.byref(module)):
            name = ctypes.create_unicode_buffer(32768)
            filename(module, name, len(name))
            return {'module': name.value, 'offset': hex(address - module.value)}
        return {'unresolved_address': hex(address or 0)}

    @ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.POINTER(Pointers))
    def observe(pointers):
        try:
            record = pointers.contents.record.contents
            if record.code == 0xC0000005:
                frames = (ctypes.c_void_p * 64)()
                count = capture(0, len(frames), frames, None)
                print(json.dumps({'native_access_violation': location(record.address),
                    'operation': int(record.information[0]),
                    'target': hex(record.information[1]),
                    'stack': [location(frames[index]) for index in range(count)]}), flush=True)
        except Exception:
            pass
        return 0  # Preserve the real native failure; never handle or retry it.

    add = kernel.AddVectoredExceptionHandler
    add.argtypes = (wintypes.ULONG, ctypes.c_void_p)
    add.restype = ctypes.c_void_p
    registration = add(1, observe)
    if not registration:
        raise ctypes.WinError(ctypes.get_last_error())
    return observe, registration
