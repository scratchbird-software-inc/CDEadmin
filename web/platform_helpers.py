##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Platform helpers that config.py needs before the application exists.

They live outside the pgadmin package so that ``import config`` does not
import the whole application (2026-11-08). pgadmin.utils re-exports them.
"""
import os

IS_WIN = (os.name == 'nt')


def env(name):
    if name in os.environ:
        return os.environ[name]
    return None


if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
    _GetShortPathNameW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD
    ]
    _GetShortPathNameW.restype = wintypes.DWORD

    def fs_short_path(_path):
        """
        Gets the short path name of a given long path.
        http://stackoverflow.com/a/23598461/200291
        """
        buf_size = len(_path)
        while True:
            res = ctypes.create_unicode_buffer(buf_size)
            # Note:- _GetShortPathNameW may return empty value
            # if directory doesn't exist.
            needed = _GetShortPathNameW(_path, res, buf_size)

            if buf_size >= needed:
                return res.value
            else:
                buf_size += needed

else:
    def fs_short_path(_path):
        return _path
