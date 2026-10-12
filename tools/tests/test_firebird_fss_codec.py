"""Preserve FSS native code units and streamed surrogate-pair boundaries."""
import codecs

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.attachment_codecs import codec_name


NAME = codec_name('UNICODE_FSS')


@pytest.mark.parametrize('text,raw', [
    ('é', 'c3a9'), ('🙂', 'eda0bdedb982'), ('𠀀', 'eda180edb080'),
    ('\ud800', 'eda080'), ('\udfff', 'edbfbf'), ('\x00', '00'),
])
def test_native_fss_encoding_and_stream_splits(text, raw):
    expected = bytes.fromhex(raw)
    assert text.encode(NAME) == expected
    assert expected.decode(NAME) == text
    for split in range(len(expected) + 1):
        decoder = codecs.getincrementaldecoder(NAME)()
        result = decoder.decode(expected[:split])
        result += decoder.decode(expected[split:], final=True)
        assert result == text


def test_native_long_sequences_narrow_to_16_bit_units():
    assert bytes.fromhex('f09f9982').decode(NAME) == '\uf642'
    assert bytes.fromhex('f0a08080').decode(NAME) == '\x00'
    assert bytes.fromhex('f888808081').decode(NAME) == '\x01'
    assert bytes.fromhex('fc8480808081').decode(NAME) == '\x01'


def test_high_surrogate_and_partial_next_character_are_retained_together():
    decoder = codecs.getincrementaldecoder(NAME)()
    assert decoder.decode(bytes.fromhex('eda0bded')) == ''
    other = codecs.getincrementaldecoder(NAME)()
    other.setstate(decoder.getstate())
    assert other.decode(bytes.fromhex('b982'), final=True) == '🙂'
    decoder.reset()
    assert decoder.decode(b'x', final=True) == 'x'


@pytest.mark.parametrize('raw', ['80', 'ff', 'c080', 'e08080', 'f0808080',
                                 'eda0', 'f88880', 'ed0042'])
def test_malformed_or_incomplete_native_fss_is_not_replaced(raw):
    with pytest.raises(UnicodeDecodeError):
        bytes.fromhex(raw).decode(NAME)
    with pytest.raises(ValueError, match='strict'):
        bytes.fromhex(raw).decode(NAME, errors='replace')
