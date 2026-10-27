"""Native host locking and durable publication of local operation receipts."""
from contextlib import contextmanager
import os
from functools import lru_cache
from pathlib import Path
import stat


@contextmanager
def exclusive_file_lock(descriptor, *, blocking=True):
    if os.name != 'nt':
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        return
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class Overlapped(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                    ('hEvent', wintypes.HANDLE)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
    kernel.LockFileEx.restype = wintypes.BOOL
    kernel.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.POINTER(Overlapped)]
    kernel.UnlockFileEx.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(descriptor)
    overlap = Overlapped()
    # Receipt writers wait by default; job admission can request immediate
    # contention reporting so its owner can cancel while waiting.
    # The stable lock file is separate from the atomically replaced JSON file.
    if not kernel.LockFileEx(handle, 2 | (0 if blocking else 1), 0, 1, 0, ctypes.byref(overlap)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not kernel.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(overlap)):
            raise ctypes.WinError(ctypes.get_last_error())


def durable_replace(source, target):
    """Publish a flushed same-volume staging file before native dispatch."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        kernel.MoveFileExW.restype = wintypes.BOOL
        # No COPY_ALLOWED: cross-volume publication cannot become non-atomic.
        if not kernel.MoveFileExW(os.fspath(source), os.fspath(target), 1 | 8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, target)
        descriptor = os.open(os.path.dirname(os.fspath(target)) or '.',
                             os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


@lru_cache(maxsize=1)
def _windows_security():
    import csv
    import ctypes
    from ctypes import wintypes
    import re
    import subprocess
    system = Path(os.environ['SystemRoot']) / 'System32'
    row = next(csv.reader(subprocess.check_output(
        [str(system / 'whoami.exe'), '/user', '/fo', 'csv', '/nh'],
        text=True, encoding='utf-8', errors='replace').splitlines()))
    sid = row[-1].strip()
    if not re.fullmatch(r'S-\d+(?:-\d+)+', sid):
        raise OSError('Current Windows user SID is unavailable')
    api = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD)]
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    api.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    api.SetFileSecurityW.restype = wintypes.BOOL
    api.GetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileSecurityW.restype = wintypes.BOOL
    api.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
    api.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    api.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)]
    api.GetSecurityDescriptorControl.restype = wintypes.BOOL
    api.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    api.GetAce.restype = wintypes.BOOL
    api.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    api.ConvertStringSidToSidW.restype = wintypes.BOOL
    api.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    api.EqualSid.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    return api, kernel, sid


def private_file(path):
    """Use mode 0600 on POSIX or a protected current-user-only Windows DACL."""
    _private_path(path, directory=False)


def private_directory(path):
    """Protect native artifacts, including newly created children on Windows."""
    _private_path(path, directory=True)


def _private_path(path, *, directory):
    if os.name != 'nt':
        os.chmod(path, 0o700 if directory else 0o600)
        return
    import ctypes
    api, kernel, sid = _windows_security()
    descriptor = ctypes.c_void_p()
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f'D:P(A;{"OICI" if directory else ""};FA;;;{sid})', 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not api.SetFileSecurityW(os.fspath(path), 4 | 0x80000000, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)


def has_private_file_permissions(path):
    """Observe the real native access policy, not synthetic Windows mode bits."""
    if os.name != 'nt':
        return stat.S_IMODE(os.stat(path).st_mode) == 0o600
    import ctypes
    from ctypes import wintypes
    api, kernel, sid = _windows_security()
    size = wintypes.DWORD()
    api.GetFileSecurityW(os.fspath(path), 4, None, 0, ctypes.byref(size))
    if not size.value:
        raise ctypes.WinError(ctypes.get_last_error())
    descriptor = ctypes.create_string_buffer(size.value)
    if not api.GetFileSecurityW(os.fspath(path), 4, descriptor, size.value, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    control, revision = wintypes.WORD(), wintypes.DWORD()
    if not api.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
        raise ctypes.WinError(ctypes.get_last_error())
    present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
    if not api.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not control.value & 0x1000 or not present.value or not dacl.value:
        return False

    class Acl(ctypes.Structure):
        _fields_ = [('revision', wintypes.BYTE), ('reserved', wintypes.BYTE),
                    ('size', wintypes.WORD), ('count', wintypes.WORD), ('reserved2', wintypes.WORD)]

    class AccessAllowedAce(ctypes.Structure):
        _fields_ = [('type', wintypes.BYTE), ('flags', wintypes.BYTE),
                    ('size', wintypes.WORD), ('mask', wintypes.DWORD)]

    if ctypes.cast(dacl, ctypes.POINTER(Acl)).contents.count != 1:
        return False
    ace = ctypes.c_void_p()
    if not api.GetAce(dacl, 0, ctypes.byref(ace)):
        raise ctypes.WinError(ctypes.get_last_error())
    policy = ctypes.cast(ace, ctypes.POINTER(AccessAllowedAce)).contents
    if policy.type != 0 or policy.flags != 0 or policy.mask != 0x1f01ff:
        return False
    user_sid = ctypes.c_void_p()
    if not api.ConvertStringSidToSidW(sid, ctypes.byref(user_sid)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # Compare binary SIDs: SDDL may render well-known users as aliases.
        return bool(api.EqualSid(ace.value + ctypes.sizeof(AccessAllowedAce), user_sid))
    finally:
        kernel.LocalFree(user_sid)
