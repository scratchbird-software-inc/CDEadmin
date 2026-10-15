"""Server conversion identity and probe transaction ownership."""
from unittest.mock import MagicMock
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird import gb18030_profile as profile
from pgadmin.cdeadmin.providers.firebird.attachment_codecs import codec_name
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def observations(name):
    codec = codec_name(name)
    rows = []
    for index, (kind, value, _) in enumerate(profile.probes()):
        try:
            raw = chr(value).encode(codec) if kind == 'encode' else value.decode(codec).encode('utf8')
        except UnicodeError:
            raw = None
        rows.append((index, raw))
    return rows


@pytest.mark.parametrize('name', ['GB18030', 'GB18030_LEGACY'])
def test_native_mapping_selects_its_qualified_profile(name):
    assert profile.select(observations(name)) == codec_name(name)


def test_native_profiles_have_different_unicode_and_alias_semantics():
    current, legacy = codec_name('GB18030'), codec_name('GB18030_LEGACY')
    assert '︐'.encode(current).hex() == 'a6d9'
    assert '︐'.encode(legacy).hex() == '84318236'
    assert bytes.fromhex('a6d9').decode(current) == '︐'
    assert bytes.fromhex('a6d9').decode(legacy) == '\ue78d'
    assert b'\x80'.decode(current) == '€'
    with pytest.raises(UnicodeDecodeError):
        b'\x80'.decode(legacy)
    for name in (current, legacy):
        assert 'ḿ︐日本🙂'.encode(name).decode(name) == 'ḿ︐日本🙂'


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unknown'])
def test_incomplete_or_unqualified_native_profile_is_refused(change):
    rows = observations('GB18030')
    if change == 'missing': rows.pop()
    elif change == 'duplicate': rows.append(rows[0])
    else: rows[0] = (rows[0][0], b'unknown')
    with pytest.raises(RelationalClientError):
        profile.select(rows)


def test_probe_uses_only_its_read_transaction_and_caches_after_release():
    connection = MagicMock()
    manager = connection.transaction_manager.return_value
    cursor = manager.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = observations('GB18030_LEGACY')
    expected = codec_name('GB18030_LEGACY')
    assert profile.encoding(connection) == expected
    assert profile.encoding(connection) == expected
    connection.transaction_manager.assert_called_once()
    manager.begin.assert_called_once()
    manager.rollback.assert_called_once()
    manager.close.assert_called_once()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    assert not connection.main_transaction.method_calls


def test_failed_probe_cleanup_cannot_cache_a_success():
    connection = MagicMock()
    manager = connection.transaction_manager.return_value
    manager.cursor.return_value.__enter__.return_value.fetchall.return_value = observations('GB18030')
    manager.close.side_effect = RuntimeError('owned cleanup failed')
    with pytest.raises(RelationalClientError) as failure:
        profile.encoding(connection)
    assert failure.value.diagnostic_cleanup_failed
    assert not isinstance(connection._cdeadmin_gb18030_encoding, str)
