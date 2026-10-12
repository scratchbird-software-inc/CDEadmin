"""Exact native conversion tables and text BLOB chunk boundaries."""
import codecs

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.attachment_codecs import (
    PRIVATE_CHARSETS, codec_name, tables,
)


@pytest.mark.parametrize('charset', sorted(
    PRIVATE_CHARSETS - {'GB18030', 'UNICODE_FSS'}))
def test_every_native_conversion_fact_and_bmp_refusal(charset):
    name = codec_name(charset)
    decoding, encoding = tables(charset)
    for raw, expected in decoding.items():
        assert raw.decode(name) == expected
    for code in range(65536):
        if code in encoding:
            assert chr(code).encode(name) == encoding[code]
        else:
            with pytest.raises(UnicodeEncodeError):
                chr(code).encode(name)
    for code in (0x10000, 0x1f642, 0x10ffff):
        with pytest.raises(UnicodeEncodeError):
            chr(code).encode(name)


def test_cp943c_native_reverse_choices_and_control_mapping():
    name = codec_name('CP943C')
    assert b'\x1a\x1c\x7f'.decode(name) == '\x1c\x7f\x1a'
    assert chr(20008).encode(name) == bytes.fromhex('fa68')
    assert chr(20008).encode('cp932') != chr(20008).encode(name)


def test_next_explicit_replacement_character_is_a_native_mapping():
    assert b'\xff'.decode(codec_name('NEXT')) == '\ufffd'


def test_tis620_is_not_python_tis620_or_cp874():
    name = codec_name('TIS620')
    assert b'\x80\xff'.decode(name) == '€\uf8c8'
    assert b'\x81'.decode(name) == '\x81'


def test_multibyte_incremental_decode_at_every_native_split():
    name = codec_name('CP943C')
    decoding, _ = tables('CP943C')
    for raw, expected in decoding.items():
        decoder = codecs.getincrementaldecoder(name)()
        parts = [decoder.decode(bytes([value]), final=False) for value in raw]
        parts.append(decoder.decode(b'', final=True))
        assert ''.join(parts) == expected
    decoder = codecs.getincrementaldecoder(name)()
    assert decoder.decode(b'\x81') == ''
    state = decoder.getstate()
    other = codecs.getincrementaldecoder(name)()
    other.setstate(state)
    assert other.decode(b'\x40', final=True) == '\u3000'
    with pytest.raises(UnicodeDecodeError):
        decoder.decode(b'', final=True)
    decoder.reset()
    assert decoder.decode(b'abc', final=True) == 'abc'


@pytest.mark.parametrize('raw', [b'\x80', b'\xff', b'\x81', b'\x81\x00'])
def test_invalid_native_cp943c_has_no_silent_fallback(raw):
    with pytest.raises(UnicodeDecodeError):
        raw.decode(codec_name('CP943C'))
    with pytest.raises(ValueError, match='strict'):
        raw.decode(codec_name('CP943C'), errors='replace')


def test_private_registration_does_not_change_driver_codec_choices():
    from firebird.driver.core import CHARSET_MAP
    assert all(name not in CHARSET_MAP for name in
               ('NEXT', 'TIS620', 'CYRL', 'CP943C'))
    with pytest.raises(ValueError):
        codec_name('UTF8')


def test_gb18030_native_revisions_and_chunk_boundaries():
    name = codec_name('GB18030')
    decoding, encoding = tables('GB18030')
    for raw, expected in decoding.items():
        assert raw.decode(name) == expected
        for split in range(len(raw) + 1):
            decoder = codecs.getincrementaldecoder(name)()
            assert (decoder.decode(raw[:split]) +
                    decoder.decode(raw[split:], final=True)) == expected
    for cp, expected in encoding.items():
        assert chr(cp).encode(name) == expected
    assert b'\x80'.decode(name) == '€'
    assert 'ḿ'.encode(name) == bytes.fromhex('a8bc')
    assert bytes.fromhex('a3a0').decode(name) == '\u3000'
    for text in ('abc', '日本', '🙂', '\U0010ffff'):
        assert text.encode(name).decode(name) == text
    for raw in (b'\x81', b'\x81\x30', b'\x81\x30\x81'):
        decoder = codecs.getincrementaldecoder(name)()
        assert decoder.decode(raw) == ''
        with pytest.raises(UnicodeDecodeError):
            decoder.decode(b'', final=True)
    for raw in (b'\xff', b'\x81\x00', b'\x81\x30\x81\x00'):
        with pytest.raises(UnicodeDecodeError):
            raw.decode(name)


@pytest.mark.parametrize('charset', sorted(
    PRIVATE_CHARSETS - {'GB18030', 'UNICODE_FSS'}))
def test_native_multibyte_incremental_boundaries(charset):
    name = codec_name(charset)
    decoding, _ = tables(charset)
    singles = {raw[0] for raw in decoding if len(raw) == 1}
    leads = {raw[0] for raw in decoding if len(raw) == 2}
    assert not singles & leads
    for raw, expected in decoding.items():
        if len(raw) != 2:
            continue
        decoder = codecs.getincrementaldecoder(name)()
        assert decoder.decode(raw[:1]) == ''
        assert decoder.decode(raw[1:], final=True) == expected
