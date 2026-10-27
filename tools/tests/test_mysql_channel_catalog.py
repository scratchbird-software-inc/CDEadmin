"""Channel facts survive discovery and exchange without credential projection."""
import json

import pytest

from test_mysql_server_catalog import Connection
from pgadmin.cdeadmin.providers.mysql_family import mysql_server_catalog
from pgadmin.cdeadmin.providers.mysql_family.installed_catalog import CHANNELS, CHANNEL_COLUMNS
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _resources
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog


def facts(name='', tls=None):
    row = dict.fromkeys((key.lower() for key in CHANNEL_COLUMNS), '')
    row.update(channel_name=name, host='localhost', port=3307, user='reader',
        connection_retry_interval=17, connection_retry_count=str(2**64-1),
        heartbeat_interval=1.25, tls_ciphersuites=tls, ssl_key="/owned/key 雪.pem",
        zstd_compression_level=7, auto_position='1', gtid_only='1')
    return row


class Channels(Connection):
    def __init__(self, rows, denied=False):
        super().__init__(); self.channel_rows = rows; self.denied = denied

    def cursor(self, **options):
        cursor = super().cursor(**options)
        def selected(source, parameters=None):
            self.calls.append(source)
            if source == CHANNELS:
                if self.denied:
                    error = RuntimeError('Private native error detail'); error.errno = 1142; error.sqlstate = '42000'; raise error
                cursor.description = [(key,) for key in CHANNEL_COLUMNS]
                cursor.rows = [tuple(row[key.lower()] for key in CHANNEL_COLUMNS) for row in self.channel_rows]
            elif source.startswith('SELECT VERSION(), @@hostname,'):
                cursor.description = []
                cursor.rows = [('9.7.0', 'owned-host', 3306, 'server-id', 'Community', 'x86_64', 'Linux', 0,
                                'InnoDB', 'REPEATABLE-READ', 'root@localhost', 'root@localhost', 'STRICT_TRANS_TABLES')]
            elif source.startswith('SELECT VERSION() AS version'):
                cursor.description = [(name,) for name in ['version', 'server_uuid', 'lower_case_table_names', 'sql_mode']]
                cursor.rows = [('9.7.0', 'server-id', 0, 'STRICT_TRANS_TABLES')]
            else:
                cursor.description = []; cursor.rows = []
        cursor.execute = selected
        def fetchall():
            rows, cursor.rows = cursor.rows, []; return rows
        cursor.fetchall = fetchall
        return cursor


@pytest.mark.parametrize('tls', [None, '', 'TLS_AES_256_GCM_SHA384'])
def test_all_channel_fields_and_exact_decimal_retry_counts_survive_ddn(tls):
    expected = facts("channel 雪'", tls)
    captured = mysql_server_catalog.capture(Channels([expected]))
    row = next(row for row in captured['resources'] if row['resource_kind'] == 'replication-channel')
    assert row['native']['catalog_row'] == expected
    exported = build_export(captured['resources'], endpoint_id='owned', target_id='server:server-id',
                            generation=captured['generation'], engine='mysql')
    restored = read_catalog(json.dumps(exported['snapshot']), engine='mysql')
    assert restored['rows'][row['resource_id']]['native']['catalog_row'] == expected
    assert len(CHANNEL_COLUMNS) == len(set(CHANNEL_COLUMNS)) == 27
    assert expected['connection_retry_count'] in json.dumps(exported['snapshot'])


@pytest.mark.parametrize('name', ['', "channel 雪'", 'group_replication_applier'])
def test_explorer_keeps_native_fields_default_identity_and_reserved_channel_read_boundary(name):
    expected = facts(name)
    rows = _resources(Channels([expected]), {'route': {}}, MYSQL_PROFILE)
    row = next(row for row in rows if row['resource_kind'] == 'replication-channel')
    assert {key: row['native'][key] for key in expected} == expected
    assert row['native']['replication_password_returned'] is False
    if name == '': assert row['display_name'] == 'Default channel'
    if name.startswith('group_replication_'):
        assert row['native']['administration']['allowed_operations'] == ['inspect']


def test_denied_channel_catalog_has_explicit_partial_coverage_without_fallback_or_private_text():
    connection = Channels([], denied=True)
    captured = mysql_server_catalog.capture(connection)
    observed = next(row for row in captured['observations'] if row['section'] == 'replication-channels')
    assert not observed['available'] and observed['error_code'] == 1142
    assert 'Private native error detail' not in json.dumps(captured)
    connection = Channels([], denied=True)
    rows = _resources(connection, {'route': {}}, MYSQL_PROFILE)
    assert not any(row['resource_kind'] == 'replication-channel' for row in rows)
    coverage = next(row for row in rows if row['resource_kind'] == 'server')['native']['catalog_coverage']
    assert coverage['state'] == 'partial' and not coverage['complete_native_inventory']
    assert not any(source.startswith('SHOW REPLICA') for source in connection.calls)


def test_projection_never_reads_replication_password_storage_or_key_contents():
    assert 'SELECT *' not in CHANNELS and 'CAST(CONNECTION_RETRY_COUNT AS CHAR)' in CHANNELS
    assert not any(token in CHANNELS.lower() for token in ['password', 'authentication_string', 'slave_master_info', 'load_file'])
    assert 'SSL_KEY' in CHANNEL_COLUMNS  # Native path, not file contents.
