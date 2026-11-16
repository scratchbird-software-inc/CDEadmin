"""Actual malformed annotation decoding, byte fidelity and native refusals."""
import base64
from contextlib import closing
from copy import deepcopy
import hashlib

import pytest
from test_mariadb_server_diagnostics import native, SETTINGS
from pgadmin.cdeadmin.providers.mysql_family.mariadb_binlog_events import read
from pgadmin.cdeadmin.providers.mysql_family.provider import _resources, MARIADB_PROFILE


@pytest.fixture
def binary_events(native):
    n = native
    n.cursor.execute('CREATE TABLE IF NOT EXISTS binlog_bytes(b BLOB)')
    n.cursor.execute('INSERT INTO binlog_bytes VALUES(?)', (b'\x00\xff\xfe\x80abc',))
    n.cursor.execute("INSERT INTO binlog_bytes VALUES('UTF8 雪')")
    n.cursor.execute('SHOW BINARY LOGS')
    names = [row[0] for row in n.cursor.fetchall()]
    yield n, names
    n.cursor.execute('DROP TABLE binlog_bytes')


def test_native_lossless_info_matches_independent_binary_charset_control(binary_events):
    n, names = binary_events
    import mariadb
    with closing(mariadb.connect(**SETTINGS)) as control:
        cursor = control.cursor(); cursor.execute('SET SESSION character_set_results=binary')
        found_binary = found_text = False
        for name in names:
            observed = read(n.cursor, name)
            assert observed['complete'] and not observed['truncated'] and not observed['session_charset_changed']
            assert not n.cursor.cdeadmin_lossless_text
            cursor.execute("SHOW BINLOG EVENTS IN '" + name + "' LIMIT 201")
            expected = cursor.fetchall()
            assert len(expected) == len(observed['events'])
            for raw, event in zip(expected, observed['events']):
                info = event['info']
                actual = base64.b64decode(info['data'], validate=True) if isinstance(info, dict) else info.encode('utf8')
                assert actual == raw[5]
                assert event['pos'] == raw[1] and event['end_log_pos'] == raw[4]
                assert event['info_native_field']['charset'] != 63
                if isinstance(info, dict):
                    assert info['byte_length'] == len(actual)
                    assert event['info_representation'] == 'undecodable-native-utf8-bytes'
                    with pytest.raises(UnicodeDecodeError):
                        actual.decode('utf8')
                    found_binary = True
                else:
                    found_text |= '雪' in info
        assert found_binary and found_text
        cursor.close()


@pytest.mark.parametrize('fetch', ['fetchone', 'fetchall', 'fetchmany'])
def test_native_decode_errors_remain_errors_in_opt_out_mode(binary_events, fetch):
    n, names = binary_events
    c = n.handle.cursor(buffered=False)
    assert c.cdeadmin_lossless_text is False
    try:
        c.execute("SHOW BINLOG EVENTS IN '" + names[-1] + "' LIMIT 201")
        with pytest.raises(UnicodeDecodeError):
            if fetch == 'fetchall':
                c.fetchall()
            else:
                while True:
                    row = c.fetchmany(100) if fetch == 'fetchmany' else c.fetchone()
                    if not row: break
    finally:
        c.close()


def test_binary_log_native_refusal_preserves_codes_and_resets_cursor(binary_events):
    n, _ = binary_events
    import mariadb
    with pytest.raises(mariadb.Error) as denied:
        read(n.cursor, 'owned-missing.000999')
    assert denied.value.errno == 1220 and denied.value.sqlstate == 'HY000'
    assert n.cursor.cdeadmin_lossless_text is False
    n.cursor.execute('SELECT 1'); assert n.cursor.fetchone() == (1,)


def test_native_catalog_returns_binary_annotation_instead_of_empty_failed_section(binary_events):
    n, _ = binary_events
    resources = _resources(n.handle, {'route': {'database': SETTINGS['database']}}, MARIADB_PROFILE)
    events = [r for r in resources if r['resource_kind'] == 'binary-log-event']
    assert any(isinstance(r['native']['info'], dict) and r['native']['info_representation'] == 'undecodable-native-utf8-bytes' for r in events)
    logs = [r for r in resources if r['resource_kind'] == 'binary-log']
    assert logs and all(r['native']['event_observation']['complete'] for r in logs)


def test_native_event_truncation_is_explicit_and_does_not_change_charset(native):
    n = native
    n.cursor.execute('FLUSH BINARY LOGS')
    n.cursor.execute('CREATE TABLE IF NOT EXISTS bounded_binlog(id INT)')
    for index in range(80):
        n.cursor.execute('INSERT INTO bounded_binlog VALUES(?)', (index,))
    n.cursor.execute('SHOW BINARY LOGS'); name = n.cursor.fetchall()[-1][0]
    n.cursor.execute('SELECT @@character_set_results'); before = n.cursor.fetchone()[0]
    observed = read(n.cursor, name)
    assert observed['truncated'] and not observed['complete']
    assert len(observed['events']) == observed['limit'] == 200
    assert not n.cursor.cdeadmin_lossless_text and not observed['automatic_retry']
    n.cursor.execute('SELECT @@character_set_results'); assert n.cursor.fetchone()[0] == before
    n.cursor.execute('DROP TABLE bounded_binlog')
