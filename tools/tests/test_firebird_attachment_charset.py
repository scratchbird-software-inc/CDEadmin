"""Native attachment charset observation, independent of alias spelling."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.attachment_charset import observe
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def connection(packet):
    attachment = Mock()
    attachment.encoding = 'ascii'
    attachment.get_info.side_effect = lambda items, buffer: setattr(
        buffer, 'raw', packet.ljust(16, b'\0'))
    return SimpleNamespace(_att=attachment, _ic=SimpleNamespace(
        _encoding='ascii'), _encoding='ascii', _Connection__charset='ALIAS')


@pytest.mark.parametrize('code,name,codec', [
    (21, 'ISO8859_1', 'iso8859_1'),
    (5, 'SJIS_0208', 'cdeadmin_firebird_5_0_4_sjis_0208'),
    (19, 'NEXT', 'cdeadmin_firebird_5_0_4_next'),
    (50, 'CYRL', 'cdeadmin_firebird_5_0_4_cyrl'),
    (66, 'TIS620', 'cdeadmin_firebird_5_0_4_tis620'),
    (68, 'CP943C', 'cdeadmin_firebird_5_0_4_cp943c'),
])
def test_observed_id_selects_codec_and_internal_cursor(code, name, codec):
    con = connection(bytes([101, 1, 0, code, 1]))
    assert observe(con) == (code, name, codec)
    assert con._encoding == con._att.encoding == con._ic._encoding == codec
    assert con._Connection__charset == name
    con._att.get_info.assert_called_once()
    assert con._att.get_info.call_args.args[0] == bytes([101])
    assert len(con._att.method_calls) == 1


@pytest.mark.parametrize('packet', [b'', b'\x65\x00\x00\x01',
                                    b'\x65\x05\x00', b'\x65\x01\x00\x04\x02',
                                    b'\x03', b'\x65\x01\x00\x01\x01',
                                    b'\x65\x01\x00\xff\x01'])
def test_invalid_or_unadmitted_observation_has_no_encoding_mutation(packet):
    con = connection(packet)
    with pytest.raises(RelationalClientError):
        observe(con)
    assert con._encoding == con._ic._encoding == 'ascii'
    assert con._Connection__charset == 'ALIAS'


def test_none_keeps_unconverted_locale_semantics():
    from firebird.driver.core import CHARSET_MAP
    con = connection(b'\x65\x01\x00\x00\x01')
    assert observe(con) == (0, 'NONE', CHARSET_MAP['NONE'])
