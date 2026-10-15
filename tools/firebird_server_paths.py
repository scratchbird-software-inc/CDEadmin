"""Interpret owned Firebird server filenames independently of the browser host."""
from pathlib import PurePosixPath, PureWindowsPath


def server_path(value):
    windows = PureWindowsPath(value)
    path = windows if windows.drive else PurePosixPath(value)
    if not path.is_absolute():
        raise ValueError('An absolute server-side database filename is required')
    return path
