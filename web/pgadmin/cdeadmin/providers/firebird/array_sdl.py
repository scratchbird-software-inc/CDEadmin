"""Explicit OCTETS fixed-width slices using Firebird's public SDL format."""
from firebird.driver import fbapi
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def octets(bounds):
    # consts_pub.h: version1, struct, relation, field, do2, long_integer,
    # element, scalar, variable, eoc. Unlike isc_array_get_slice's generated
    # dynamic text descriptor, text2 explicitly fixes the charset to OCTETS.
    count = bounds.array_desc_dimensions
    if not 1 <= count <= 16 or not 1 <= bounds.array_desc_length <= 65535:
        raise RelationalClientError('Invalid OCTETS array descriptor')
    result = bytearray([1, 6, 1, fbapi.blr_text2, 1, 0])
    result.extend(bounds.array_desc_length.to_bytes(2, 'little'))
    for tag, name in ((2, bounds.array_desc_relation_name),
                      (4, bounds.array_desc_field_name)):
        if not name or len(name) > 255:
            raise RelationalClientError('Invalid OCTETS array source name')
        result.extend([tag, len(name)])
        result.extend(name)
    for index in range(count):
        bound = bounds.array_desc_bounds[index]
        if bound.array_bound_upper < bound.array_bound_lower:
            raise RelationalClientError('Invalid OCTETS array bounds')
        result.extend([34, index, 11])
        result.extend(bound.array_bound_lower.to_bytes(
            4, 'little', signed=True))
        result.append(11)
        result.extend(bound.array_bound_upper.to_bytes(
            4, 'little', signed=True))
    result.extend([36, 1, 8, 0, count])
    for index in range(count):
        result.extend([7, index])
    result.append(255)
    return bytes(result)
