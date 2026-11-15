"""Installed public-API bridge; captures only a staged driver-owned native open."""
import os
import sqlite3
import sqlite_native_component as component
from ...sdk import RelationalClientError

installed_library=component.installed_library


def load_optional():
    import config
    filename=getattr(config,'CDEADMIN_SQLITE_CONFIG_LIBRARY','') or os.environ.get('CDEADMIN_SQLITE_CONFIG_LIBRARY','') or installed_library()
    if not filename:return None
    loaded=component.load(filename)
    if loaded.program['sqlite_version']!=sqlite3.sqlite_version:
        raise RelationalClientError('Native helper loaded a different SQLite runtime')
    return loaded


class ConfigurationBridge:
    def __init__(self,loaded,capsule):
        self.component=loaded;self.module=loaded.module;self.program=dict(loaded.program);self.capsule=capsule
        self.closed=False;self.reviews={};self.last_lookaside_request=None;self.main_alias_changes=0

    def release(self,connection):
        if not self.closed:
            self.module.closed(self.capsule,connection)
            self.closed=True;self.reviews.clear();self.component.release()


def before_open():
    loaded=load_optional()
    if loaded is None:return None
    loaded.retain()
    try:return [loaded,loaded.module.begin(),False]
    except BaseException:loaded.release();raise


def finish_open(staged,connection):
    if staged is None:return None
    loaded,capsule,_=staged
    loaded.module.finish(capsule,connection)
    bridge=ConfigurationBridge(loaded,capsule)
    staged[2]=True
    return bridge


def cancel_open(staged):
    if staged is not None and not staged[2]:
        staged[0].module.cancel(staged[1]);staged[0].release();staged[2]=True
