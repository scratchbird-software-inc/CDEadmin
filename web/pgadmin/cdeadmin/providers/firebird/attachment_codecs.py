"""Exact private codecs for native attachment charsets."""
import codecs
from functools import lru_cache
import json
from pathlib import Path
from types import MappingProxyType


PREFIX = 'cdeadmin_firebird_5_0_4_'
PRIVATE_CHARSETS = frozenset({
    'UNICODE_FSS',
    'BIG_5',
    'CP943C',
    'CYRL',
    'DOS857',
    'DOS864',
    'DOS869',
    'EUCJ_0208',
    'GB18030',
    'GBK',
    'GB_2312',
    'ISO8859_3',
    'ISO8859_6',
    'ISO8859_7',
    'ISO8859_8',
    'KOI8U',
    'KSC_5601',
    'NEXT',
    'SJIS_0208',
    'TIS620',
    'WIN1250',
    'WIN1251',
    'WIN1252',
    'WIN1253',
    'WIN1254',
    'WIN1255',
    'WIN1257',
    'WIN1258',
})


@lru_cache(maxsize=1)
def _document():
    return json.loads(Path(__file__).with_name(
        'attachment_codec_tables_5_0_4.json').read_text())


def native_name(identifier):
    return _document()['charsets'].get(str(identifier))


@lru_cache(maxsize=32)
def tables(name):
    table = _document()['tables'][name]
    return (MappingProxyType({bytes.fromhex(key): chr(value)
                              for key, value in table['decode'].items()}),
            MappingProxyType({int(key): bytes.fromhex(value)
                              for key, value in table['encode'].items()}))


def _codec(name):
    decoding, encoding = tables(name)
    leads = frozenset(key[0] for key in decoding if len(key) == 2)
    codec_name = PREFIX + name.lower()
    gb18030 = name == 'GB18030'

    def strict(errors):
        if errors != 'strict':
            raise ValueError(
                'Native Firebird codecs require strict conversion')

    def encode(value, errors='strict'):
        strict(errors)
        output = bytearray()
        for index, char in enumerate(value):
            packed = encoding.get(ord(char))
            if packed is None and gb18030:
                try:
                    packed = char.encode('gb18030')
                except UnicodeEncodeError:
                    pass
            if packed is None:
                raise UnicodeEncodeError(codec_name, value, index, index + 1,
                                         'not representable natively')
            output.extend(packed)
        return bytes(output), len(value)

    def decode(value, errors='strict', final=True):
        strict(errors)
        data = bytes(value)
        output = []
        index = 0
        while index < len(data):
            width = 2 if data[index] in leads else 1
            if gb18030 and 0x81 <= data[index] <= 0xfe:
                width = 2
                if index + 1 < len(data) and 0x30 <= data[index + 1] <= 0x39:
                    width = 4
            if index + width > len(data):
                if not final:
                    break
                raise UnicodeDecodeError(codec_name, data, index, len(data),
                                         'incomplete native character')
            text = decoding.get(data[index:index + width])
            if text is None and gb18030:
                try:
                    text = data[index:index + width].decode('gb18030')
                except UnicodeDecodeError:
                    pass
            if text is None:
                raise UnicodeDecodeError(
                    codec_name, data, index, index + width,
                    'invalid native character')
            output.append(text)
            index += width
        return ''.join(output), index

    class IncrementalDecoder(codecs.BufferedIncrementalDecoder):
        def _buffer_decode(self, data, errors, final):
            return decode(data, errors, final)

    class IncrementalEncoder(codecs.IncrementalEncoder):
        def encode(self, value, final=False):
            return encode(value, self.errors)[0]

    return codecs.CodecInfo(
        name=codec_name, encode=encode, decode=decode,
        incrementalencoder=IncrementalEncoder,
        incrementaldecoder=IncrementalDecoder)


def _search(name):
    if name.startswith(PREFIX):
        charset = name[len(PREFIX):].upper()
        if charset == 'UNICODE_FSS':
            from .fss_codec import codec
            return codec()
        if charset in PRIVATE_CHARSETS:
            return _codec(charset)
    return None


codecs.register(_search)


def codec_name(charset):
    if charset not in PRIVATE_CHARSETS:
        raise ValueError('No private native codec for this character set')
    return PREFIX + charset.lower()
