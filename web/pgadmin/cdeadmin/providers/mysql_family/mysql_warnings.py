"""Keep the native pure warning handler compatible with Python regex filters.

Connector26.7 passes its Exception-derived Warning directly to warnings.warn.
Python warning message filters require text (or a built-in Warning instance).
Reuse the native function with a private warnings port, without changing its
native fetch/error behavior or the process-wide warning module and filters.
"""
from functools import lru_cache
from types import FunctionType,MethodType
import warnings


class WarningPort:
    def warn(self,message,*args,**kwargs):
        if isinstance(message,Exception) and not isinstance(message,Warning):message=str(message)
        # This port introduces one frame before the unchanged native call.
        if len(args)<2:kwargs['stacklevel']=kwargs.get('stacklevel',1)+1
        return warnings.warn(message,*args,**kwargs)


@lru_cache(maxsize=16)
def adapted(function):
    namespace=dict(function.__globals__);namespace['warnings']=WarningPort()
    return FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)


def install(cursor):
    original=getattr(type(cursor),'_handle_warnings',None)
    if isinstance(original,FunctionType) and original.__module__=='mysql.connector.cursor' and original.__globals__.get('warnings') is warnings:
        cursor._handle_warnings=MethodType(adapted(original),cursor)
