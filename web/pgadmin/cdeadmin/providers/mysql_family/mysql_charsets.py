"""Native SQL charset observations for Connector/Python26.7 text cursors.

The pure protocol exposes system-variable changes in negotiated OK packets;
the C client exposes its current native character set without another query.
Never send SET NAMES or overwrite the operator's session settings here.
"""
import codecs
from contextvars import ContextVar
import weakref

from ...sdk import RelationalClientError


_LATIN1_DECODE={byte:ord(bytes([byte]).decode('cp1252')) for byte in range(128,160) if byte not in {129,141,143,144,157}}
_LATIN1_ENCODE={chr(_LATIN1_DECODE.get(byte,byte)):byte for byte in range(256)}


def _latin_encode(value,errors='strict'):
    result=bytearray()
    for index,char in enumerate(value):
        byte=_LATIN1_ENCODE.get(char)
        if byte is None:
            error=UnicodeEncodeError('mysql_latin1',value,index,index+1,'character is not in native MySQL latin1')
            replacement,_position=codecs.lookup_error(errors)(error)
            result.extend(replacement if isinstance(replacement,bytes) else _latin_encode(replacement,errors)[0])
        else:result.append(byte)
    return bytes(result),len(value)


def _latin_decode(value,errors='strict'):
    value=bytes(value);return value.decode('latin1').translate(_LATIN1_DECODE),len(value)


def _codec(name):
    if name=='cdeadmin_mysql_latin1':return codecs.CodecInfo(name=name,encode=_latin_encode,decode=_latin_decode)


codecs.register(_codec)


def codec(name):
    if name in {'utf8','utf8mb3','utf8mb4','binary',None}:return 'utf8'
    if name=='latin1':return 'cdeadmin_mysql_latin1'
    aliases={'ujis':'euc_jp','eucjpms':'euc_jp','sjis':'shift_jis','ucs2':'utf_16_be','utf16':'utf_16_be','utf16le':'utf_16_le','utf32':'utf_32_be'}
    return aliases.get(name,name)


def parameter_values(values, charset):
    """Retain native values while encoding MySQL's non-Python latin1 text."""
    if charset != 'latin1':
        return values
    def encoded(value):
        return value.encode(codec(charset)) if isinstance(value, str) else value
    if isinstance(values, dict):
        return {key: encoded(value) for key, value in values.items()}
    if isinstance(values, (tuple, list)):
        return type(values)(encoded(value) for value in values)
    return values


def install(native):
    if not type(native).__module__.startswith('mysql.connector.'):return
    reference=weakref.ref(native);factory=type(native).cursor
    creating_cursor=ContextVar('cdeadmin_mysql_creating_cursor',default=False)
    c_api=getattr(native,'_cmysql',None)
    initial=factory(native)
    try:
        initial.execute('SELECT @@SESSION.character_set_client,@@SESSION.character_set_connection,@@SESSION.character_set_results')
        client,connection,results=initial.fetchone();initial.fetchall()
    finally:initial.close()
    native._cdeadmin_charset_variables={'character_set_client':client,'character_set_connection':connection,'character_set_results':results}

    def refresh_c_variables():
        owner=reference()
        if owner is None:raise RelationalClientError('MySQL character-set connection is unavailable')
        from .mysql_session_variables import observe
        observed = observe(owner)
        if observed is not None:
            owner._cdeadmin_charset_variables = {key: observed['variables'][key] for key in owner._cdeadmin_charset_variables}
            return
        metadata=factory(owner,raw=True)
        try:
            metadata.execute('SELECT @@SESSION.character_set_client,@@SESSION.character_set_connection,@@SESSION.character_set_results')
            values=metadata.fetchone();metadata.fetchall()
            owner._cdeadmin_charset_variables=dict(zip(('character_set_client','character_set_connection','character_set_results'),
                (None if value is None else value.decode('ascii') if isinstance(value,bytes) else value for value in values)))
        finally:metadata.close()

    def sync():
        owner=reference()
        if owner is None:raise RelationalClientError('MySQL character-set connection is unavailable')
        values=owner._cdeadmin_charset_variables
        name=c_api.character_set_name() if c_api is not None else values['character_set_client']
        if isinstance(name,bytes):name=name.decode('ascii')
        owner._charset_id=owner._character_set.get_charset_info(name)[0]
        converter=getattr(owner,'converter',None)
        if converter is not None:converter.set_charset(name,character_set=owner._character_set)
        return name

    if c_api is None:
        from mysql.connector import utils
        from mysql.connector.constants import ServerFlag
        protocol=native._protocol;parse_ok=type(protocol).parse_ok;parse_column=type(protocol).parse_column
        def observed_ok(packet):
            result=parse_ok(packet)
            if result['status_flag'] & ServerFlag.SERVER_SESSION_STATE_CHANGED:
                owner=reference()
                if owner is None:raise RelationalClientError('MySQL character-set connection is unavailable')
                rest,_value=utils.read_lc_int(packet[5:]);rest,_value=utils.read_lc_int(rest)
                rest=rest[4:];rest,_info=utils.read_lc_string(rest)
                if rest:
                    _rest,changes=utils.read_lc_string(rest)
                    while changes:
                        kind=changes[0];changes,block=utils.read_lc_string(changes[1:])
                        if kind==0:
                            while block:
                                block,key=utils.read_lc_string(block);block,value=utils.read_lc_string(block)
                                key=key.decode('ascii')
                                if key in owner._cdeadmin_charset_variables:
                                    value=value.decode('ascii');owner._cdeadmin_charset_variables[key]=None if value in {'NULL',''} else value
                    sync()
            return result
        def observed_column(packet,encoding='utf-8'):
            owner=reference()
            if owner is None:raise RelationalClientError('MySQL result character-set connection is unavailable')
            return parse_column(packet,codec(owner._cdeadmin_charset_variables['character_set_results']))
        protocol.parse_ok=observed_ok;protocol.parse_column=observed_column
        class NativeColumnConverter(type(native.converter)):
            def _string_to_python(self,value,dsc=None):
                if not self.use_unicode or dsc is None:return value
                from mysql.connector.constants import FieldFlag,FieldType
                if dsc[1]==FieldType.JSON:return value.decode('utf8')
                if dsc[8]==63:return value
                from .mysql_values import decode_text
                decoded=decode_text(value,dsc[8])
                if not isinstance(decoded,str):return value
                return set(decoded.split(',')) if dsc[7]&FieldFlag.SET and decoded else set() if dsc[7]&FieldFlag.SET else decoded
            _var_string_to_python=_string_to_python
            _json_to_python=_string_to_python
            _blob_to_python=_string_to_python
            _set_to_python=_string_to_python
        native.set_converter_class(NativeColumnConverter)

    if c_api is not None:
        original_columns=type(native).fetch_eof_columns;original_rows=type(native).get_rows
        def raw_columns(prep_stmt=None):
            owner=reference()
            if owner is None:raise RelationalClientError('MySQL result metadata connection is unavailable')
            if prep_stmt is not None:return original_columns(owner,prep_stmt)
            unicode=c_api.use_unicode();c_api.use_unicode(False)
            try:result=original_columns(owner,prep_stmt)
            finally:c_api.use_unicode(unicode)
            result_codec=codec(owner._cdeadmin_charset_variables['character_set_results'])
            client=owner._cdeadmin_charset_variables['character_set_client']
            # The C extension may have cached fields during row fetching. Its
            # Python Latin1 decoder differs from the native MySQL mapping.
            client_codec='latin1' if client=='latin1' else codec(client)
            columns=[]
            for field in result['columns']:
                name=field[0]
                wire=name if isinstance(name,bytes) else name.encode(client_codec)
                columns.append((wire.decode(result_codec),*field[1:]))
            owner._columns=columns;result['columns']=columns
            return result
        def observed_rows(*args,**kwargs):
            owner=reference()
            if owner is None:raise RelationalClientError('MySQL result connection is unavailable')
            requested_raw=kwargs.get('raw',args[3] if len(args)>3 else None)
            effective_raw=bool(owner._raw or c_api.raw()) if requested_raw is None else requested_raw
            unicode=c_api.use_unicode();c_api.use_unicode(False)
            try:rows,eof=original_rows(owner,*args,**kwargs)
            finally:c_api.use_unicode(unicode)
            if unicode and not effective_raw:
                from .mysql_values import decode_text
                from mysql.connector.constants import FieldType
                text_types={FieldType.STRING,FieldType.VAR_STRING,FieldType.VARCHAR,FieldType.ENUM,FieldType.SET,FieldType.TINY_BLOB,FieldType.MEDIUM_BLOB,FieldType.LONG_BLOB,FieldType.BLOB}
                def converted(value,column):
                    if isinstance(value,bytes) and column[8]!=63 and column[1] in text_types:
                        return decode_text(value,column[8])
                    if isinstance(value,set):return {decode_text(item,column[8]) if isinstance(item,bytes) else item for item in value}
                    if isinstance(value,bytes) and column[1]==FieldType.JSON:return value.decode('utf8')
                    return value
                rows=[tuple(converted(value,column) for value,column in zip(row,owner._columns)) for row in rows]
            return rows,eof
        native.fetch_eof_columns=raw_columns;native.get_rows=observed_rows

    def owned_cursor(*args,**kwargs):
        owner=reference()
        if owner is None:raise RelationalClientError('MySQL character-set connection is unavailable')
        sync()
        construction=creating_cursor.set(True)
        try:cursor=factory(owner,*args,**kwargs)
        finally:creating_cursor.reset(construction)
        if c_api is None:
            from .mysql_warnings import install as install_warnings
            install_warnings(cursor)
        if any('Prepared' in cls.__name__ for cls in type(cursor).__mro__):return cursor
        cursor_reference=weakref.ref(cursor)
        def adapted(method,many=False):
            def execute_text(operation,*arguments,**keywords):
                cursor=cursor_reference()
                if cursor is None:raise RelationalClientError('MySQL character-set cursor is unavailable')
                if c_api is not None:refresh_c_variables()
                name=sync()
                if isinstance(operation,str) and not many:operation=operation.encode(codec(name))
                def row(value):return parameter_values(value,name)
                def parameters(value):
                    if not many:return row(value)
                    return type(value)(row(item) for item in value) if isinstance(value,(tuple,list)) else (row(item) for item in value)
                if arguments:arguments=(parameters(arguments[0]),*arguments[1:])
                for key in ('params','seq_params'):
                    if key in keywords:keywords[key]=parameters(keywords[key])
                return method(cursor,operation,*arguments,**keywords)
            return execute_text
        cursor.execute=adapted(type(cursor).execute)
        cursor.executemany=adapted(type(cursor).executemany,True)
        return cursor
    base=type(native)
    class CharsetConnection(base):
        @property
        def python_charset(self):return codec(self._character_set.get_info(self._charset_id)[0])
        def is_connected(self):
            if creating_cursor.get():
                # The native cursor factory sends PING through is_connected().
                # Constructing a cursor must preserve the user's ROW_COUNT and
                # diagnostic area. Check local closure here; actual execution
                # owns transport failure handling and never reconnects.
                return bool(c_api.connected()) if c_api is not None else self._socket is not None
            return super().is_connected()
    CharsetConnection.__name__='Charset'+base.__name__
    native.__class__=CharsetConnection
    native.cursor=owned_cursor
    native._cdeadmin_sync_charset=sync
    sync()
