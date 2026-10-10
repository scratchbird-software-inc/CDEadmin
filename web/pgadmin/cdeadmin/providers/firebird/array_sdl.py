"""Explicit OCTETS fixed-width slices using Firebird's public SDL format."""
from firebird.driver import fbapi
from .array_layout import program
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def octets(bounds):
    return text_slice(bounds, 1)


def transport_charset(cursor):
    if (getattr(cursor._connection, 'charset', None) == 'UNICODE_FSS' and
            cursor._encoding == 'utf8'):
        return 4
    return 127


def text_slice(bounds, charset, *, cstring=False):
    # consts_pub.h: version1, struct, relation, field, do2, long_integer,
    # element, scalar, variable, eoc. Unlike isc_array_get_slice's generated
    # dynamic text descriptor, text2/cstring2 explicitly set the charset.
    count = bounds.array_desc_dimensions
    if not 1 <= count <= 16 or not 1 <= bounds.array_desc_length <= 65535:
        raise RelationalClientError('Invalid OCTETS array descriptor')
    if type(charset) is not int or not 0 <= charset <= 65535:
        raise RelationalClientError('Invalid slice character set')
    descriptor = bytearray([
        fbapi.blr_cstring2 if cstring else fbapi.blr_text2])
    descriptor.extend(charset.to_bytes(2, 'little'))
    descriptor.extend(bounds.array_desc_length.to_bytes(2, 'little'))
    return program(bounds, descriptor)
