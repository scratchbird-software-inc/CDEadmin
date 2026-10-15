"""Confine server-side creation paths without using the application's OS paths."""
import ntpath
import posixpath

from ...sdk.relational import RelationalClientError


def parent_path(filename):
    paths = ntpath if ntpath.splitdrive(filename)[0] else posixpath
    return paths.dirname(filename) if paths.isabs(filename) else None


def resolve(root, requested):
    windows = bool(ntpath.splitdrive(root)[0])
    paths = ntpath if windows else posixpath
    root = paths.normpath(root)
    if not paths.isabs(root) or (windows and not ntpath.splitdrive(root)[0]):
        raise RelationalClientError('Firebird database creation root must be absolute')
    drive = ntpath.splitdrive(requested)[0]
    if windows and ((bool(drive) != paths.isabs(requested)) or
                    (requested.startswith(('\\', '/')) and not drive)):
        raise RelationalClientError('Firebird database filename must be relative or fully absolute')
    database = paths.normpath(requested if paths.isabs(requested) else paths.join(root, requested))
    try:
        confined = paths.normcase(paths.commonpath((root, database))) == paths.normcase(root)
    except ValueError:
        confined = False
    if not confined:
        raise RelationalClientError('database file escapes the approved creation root')
    return database
