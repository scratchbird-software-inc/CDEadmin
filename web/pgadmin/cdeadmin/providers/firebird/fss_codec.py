"""Firebird UNICODE_FSS: native FSS sequences over UTF-16 code units."""
import codecs


NAME = 'cdeadmin_firebird_5_0_4_unicode_fss'


def strict(errors):
    if errors != 'strict':
        raise ValueError('Native Firebird codecs require strict conversion')


def encode(value, errors='strict'):
    strict(errors)
    units = value.encode('utf-16-le', 'surrogatepass')
    output = bytearray()
    for offset in range(0, len(units), 2):
        unit = int.from_bytes(units[offset:offset + 2], 'little')
        output.extend(chr(unit).encode('utf-8', 'surrogatepass'))
    return bytes(output), len(value)


def decode(value, errors='strict', final=True):
    strict(errors)
    data = bytes(value)
    units = bytearray()
    index = last_start = 0
    while index < len(data):
        start = index
        first = data[start]
        if first < 0x80:
            width, code, minimum = 1, first, 0
        elif 0xc0 <= first <= 0xdf:
            width, code, minimum = 2, first & 0x1f, 0x80
        elif 0xe0 <= first <= 0xef:
            width, code, minimum = 3, first & 0x0f, 0x800
        elif 0xf0 <= first <= 0xf7:
            width, code, minimum = 4, first & 7, 0x10000
        elif 0xf8 <= first <= 0xfb:
            width, code, minimum = 5, first & 3, 0x200000
        elif 0xfc <= first <= 0xfd:
            width, code, minimum = 6, first & 1, 0x4000000
        else:
            raise UnicodeDecodeError(NAME, data, start, start + 1,
                                     'invalid native FSS lead byte')
        if start + width > len(data):
            if not final:
                break
            raise UnicodeDecodeError(NAME, data, start, len(data),
                                     'incomplete native FSS character')
        for part in data[start + 1:start + width]:
            if part & 0xc0 != 0x80:
                raise UnicodeDecodeError(NAME, data, start, start + width,
                                         'invalid native FSS continuation')
            code = (code << 6) | (part & 0x3f)
        if code < minimum:
            raise UnicodeDecodeError(NAME, data, start, start + width,
                                     'overlong native FSS character')
        # Native fss_mbtowc writes into a 16-bit UNICODE destination.
        units.extend((code & 0xffff).to_bytes(2, 'little'))
        last_start = start
        index += width
    if not final and units:
        last = int.from_bytes(units[-2:], 'little')
        if 0xd800 <= last <= 0xdbff:
            del units[-2:]
            index = last_start
    return units.decode('utf-16-le', 'surrogatepass'), index


class IncrementalDecoder(codecs.BufferedIncrementalDecoder):
    def _buffer_decode(self, data, errors, final):
        return decode(data, errors, final)


class IncrementalEncoder(codecs.IncrementalEncoder):
    def encode(self, value, final=False):
        return encode(value, self.errors)[0]


def codec():
    return codecs.CodecInfo(
        name=NAME, encode=encode, decode=decode,
        incrementalencoder=IncrementalEncoder,
        incrementaldecoder=IncrementalDecoder)
