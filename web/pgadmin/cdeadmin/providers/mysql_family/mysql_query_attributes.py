"""Scoped native query attributes and guarded pure-driver packet metadata.

The pinned pure driver's COM_QUERY path omits NULL names/metadata. Its ordinary
binary parameter encoder handles NULL correctly. Reuse that encoder locally;
send one native COM_QUERY with the original SQL and correctly framed attributes.
No prepared statement or additional SQL is sent by this packet adapter.
"""
from copy import deepcopy
import datetime
import json

from .mysql_values import MySQLParameterAdmissionError, parameters
from .mysql_charsets import codec


class AttributeAdmissionError(MySQLParameterAdmissionError):
    query_attributes_admission = True


def request_value(value):
    if not isinstance(value,dict) or len(value)>65535 or any(not isinstance(name,str) or '\0' in name for name in value):
        raise ValueError('MySQL query attributes require a JSON object of names and values')
    try:size=len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8'))
    except (ValueError,TypeError,UnicodeError,RecursionError):
        raise ValueError('MySQL query attributes require bounded JSON values and valid Unicode') from None
    if size>2*1024*1024:raise ValueError('MySQL query attributes exceed 2 MiB')
    return deepcopy(value)


def decoded(value):
    try:result=parameters(request_value(value))
    except Exception:
        raise AttributeAdmissionError('Native MySQL query attribute values could not be admitted before dispatch') from None
    if any(type(item) is int and not -(2**63)<=item<=2**64-1 for item in result.values()):
        raise AttributeAdmissionError('Native MySQL integer attributes require 64-bit values; use a decimal envelope for larger exact numbers')
    return result


class AttributeName(str):
    """Keep selected source-charset bytes through the native SDK encoders."""
    def __new__(cls,value,wire=None):
        result=super().__new__(cls,value);result.wire=wire
        return result
    def encode(self, *_args, **_kwargs):return self.wire if self.wire is not None else str(self).encode('utf8')


def c_attributes_abi():
    try:
        import _mysql_connector
    except ImportError:
        return 0
    return 1 if getattr(_mysql_connector, 'CDEADMIN_QUERY_ATTRIBUTES_ABI', None) == 1 else 0


def packet(protocol, source, attributes):
    from mysql.connector.utils import lc_int
    nulls=bytearray((len(attributes)+7)//8);metadata=[];values=[]
    for index,(name,value) in enumerate(attributes):
        # This is serialization only, using the selected native driver's
        # ordinary binary encoder. Statement ID zero is never sent to a server.
        # Connector 26.7 serializes negative timedelta using Python's normalized
        # negative days and positive seconds. Encode the positive magnitude with
        # its native encoder, then set only the protocol's explicit sign byte.
        negative=isinstance(value,datetime.timedelta) and value<datetime.timedelta()
        encoded=protocol.make_stmt_execute(0,data=(-value if negative else value,),parameters=(None,),charset='utf8')
        if (not isinstance(encoded,bytes) or len(encoded)<13 or
                encoded[:9]!=b'\0\0\0\0\0\1\0\0\0' or encoded[9] not in (0,1) or encoded[10]!=1):
            raise AttributeAdmissionError('The native MySQL binary attribute encoder layout differs')
        if encoded[9]:nulls[index//8]|=1<<(index%8)
        if negative:
            if encoded[11]!=11 or encoded[13] not in (8,12) or encoded[14]!=0:
                raise AttributeAdmissionError('The native MySQL TIME attribute encoder layout differs')
            encoded=encoded[:14]+b'\1'+encoded[15:]
        raw_name=name.encode('utf8')
        metadata.append(encoded[11:13]+lc_int(len(raw_name))+raw_name)
        values.append(encoded[13:])
    return (lc_int(len(attributes))+lc_int(1)+
        (bytes(nulls)+b'\1'+b''.join(metadata)+b''.join(values) if attributes else b'')+source)


class Scope:
    def __init__(self, connection, values):
        self.connection=connection;self.values=values;self.before=None;self.active=False
        self.send=None;self.send_override=False;self.old_send_present=False;self.old_send=None

    def install(self):
        connection=self.connection
        before=getattr(connection,'query_attrs',None)
        if not isinstance(before,list):
            if self.values:raise AttributeAdmissionError('This MySQL client has no native query-attribute port')
            return
        if self.values:
            if getattr(connection,'_cmysql',None) is not None and c_attributes_abi() != 1:
                raise AttributeAdmissionError('Native C query attributes require the corrected Connector/Python 26.7 extension; build it with cdeadmin_build_mysql_driver')
            from mysql.connector.constants import ClientFlag
            flags=getattr(connection,'client_flags',0);handshake=getattr(connection,'_handshake',{}) or {}
            native_flags=getattr(getattr(connection,'_cmysql',None),'st_client_flag',None)
            if callable(native_flags):flags=native_flags()
            if (type(flags) is not int or type(handshake.get('capabilities')) is not int or
                    not flags & handshake['capabilities'] & ClientFlag.CLIENT_QUERY_ATTRIBUTES):
                raise AttributeAdmissionError('Native MySQL query attributes were not negotiated')
        self.before=list(before);self.active=True
        connection.query_attrs_clear()
        if self.values and getattr(connection,'_cmysql',None) is None:
            self.send=connection._send_cmd
            self.old_send_present='_send_cmd' in connection.__dict__
            self.old_send=connection.__dict__.get('_send_cmd')
            connection._send_cmd=self._send
            self.send_override=True

    def _send(self, command, argument=None, *args, **kwargs):
        from mysql.connector.constants import ServerCmd
        if command==ServerCmd.QUERY:
            source=getattr(self.connection,'_query',None)
            if (not isinstance(source,(bytes,bytearray)) or not isinstance(argument,(bytes,bytearray)) or
                    not bytes(argument).endswith(bytes(source)) or kwargs.get('packet') is not None):
                raise AttributeAdmissionError('The native MySQL query packet layout differs before dispatch')
            try:argument=packet(self.connection._protocol,bytes(source),self.connection.query_attrs)
            except AttributeAdmissionError:raise
            except Exception:
                raise AttributeAdmissionError('Native MySQL query attributes could not be encoded before dispatch') from None
        return self.send(command,argument,*args,**kwargs)

    def bind(self):
        if not self.active:return
        connection=self.connection;connection.query_attrs_clear()
        if not self.values:return
        from .mysql_session_variables import observe
        observation=observe(connection)
        if observation is not None:
            charset=observation['variables']['character_set_client']
        else:
            # The pre-existing unadmitted observation profile is not qualified
            # for diagnostic preservation. Do not label its original reads as
            # an independent observation; admitted failures never use this path.
            cursor=connection.cursor()
            try:
                cursor.execute('SELECT @@SESSION.character_set_client');charset=cursor.fetchone()[0]
                if isinstance(charset,bytes):charset=charset.decode('ascii')
            finally:cursor.close()
        try:
            for name,value in self.values.items():
                native_name=name.encode(codec(charset))
                if isinstance(value,str):value=value.encode(codec(charset))
                connection.query_attrs_append((AttributeName(name,native_name),value))
            if self.send_override:packet(connection._protocol,b'',connection.query_attrs)
        except AttributeAdmissionError:raise
        except Exception:
            raise AttributeAdmissionError('A native MySQL query attribute cannot be encoded in the current client character set') from None

    def restore(self):
        if not self.active:return
        problems=[];connection=self.connection
        if self.send_override:
            try:
                if self.old_send_present:connection._send_cmd=self.old_send
                else:del connection._send_cmd
            except Exception:problems.append(True)
        try:
            connection.query_attrs_clear()
            for value in self.before:connection.query_attrs_append(value)
            if connection.query_attrs!=self.before:problems.append(True)
        except Exception:problems.append(True)
        self.active=False
        if problems:raise RuntimeError('Native MySQL query attribute state restoration is unconfirmed')
