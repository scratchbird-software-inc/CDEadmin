"""Observe native attachment character set before provider SQL."""
from ctypes import create_string_buffer

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .attachment_codecs import PRIVATE_CHARSETS, codec_name, native_name


ATT_CHARSET = 101


def observe(connection):
    from firebird.driver.core import CHARSET_MAP

    buffer = create_string_buffer(16)
    connection._att.get_info(bytes([ATT_CHARSET]), buffer)
    raw = buffer.raw
    length = int.from_bytes(raw[1:3], 'little')
    if (raw[0] != ATT_CHARSET or not 1 <= length <= 4 or
            raw[3 + length] != 1):
        raise RelationalClientError(
            'Native attachment character set observation is invalid')
    identifier = int.from_bytes(raw[3:3 + length], 'little')
    name = native_name(identifier)
    if name is None or name == 'OCTETS':
        raise RelationalClientError(
            'Native attachment character set is not admitted')
    encoding = (codec_name(name) if name in PRIVATE_CHARSETS
                else CHARSET_MAP[name])
    # Connection construction creates its private query cursor before provider
    # initialization. Update that existing cursor as well as future cursors.
    connection._encoding = encoding
    connection._att.encoding = encoding
    connection._ic._encoding = encoding
    connection._Connection__charset = name
    return identifier, name, encoding
