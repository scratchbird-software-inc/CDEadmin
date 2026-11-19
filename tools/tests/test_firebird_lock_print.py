"""Unit tests for Firebird fb_lock_print structured diagnostics and journal."""
import json
from pathlib import Path
import pytest

from pgadmin.cdeadmin.providers.firebird import lock_print as lp
from pgadmin.cdeadmin.workspace.firebird_lock_print_actions import LockPrintActions


SAMPLE_SNAPSHOT = """LOCK_HEADER BLOCK
\tVersion: 147, Creation timestamp: 2026-11-18 18:44:54
\tActive owner:      0, Length: 1048576, Used: 147704
\tEnqs:    632, Converts:     14, Rejects:      5, Blocks:    114
\tDeadlock scans:      0, Deadlocks:      0, Scan interval:  10
\tAcquires:   1202, Acquire blocks:    106, Spin count:   0
\tMutex wait: 8.8%
\tHash slots: 8191, Hash lengths (min/avg/max):    0/   0/   8
\tOwners (2):\tforward:  78400, backward:  99656

OWNER BLOCK  99656
\tOwner id: 6727641067421697, Type: 1
\tProcess id: 1566401 (Alive), Thread id: 1566401
\tFlags: 0x00                
\tRequests (213):\tforward:  97576, backward: 147632
\tBlocks: *empty*
\tPending (1):\tforward: 147632, backward: 147632
         99656 waits on 
             78400 waits on nothing.

REQUEST BLOCK  78584
\tOwner:  78400, Lock:  78656, State: 4, Mode: 4, Flags: 0x00
\tAST: 0x0x7f3b2c8148c0, argument: 0x0x7f3b2f21f8c0

LOCK BLOCK  98480
\tSeries: 4, State: 6, Size: 16, Length: 8, Data: 3
\tKey: 000000003, Flags: 0x00, Pending request count:      1
\tRequests (2):\tforward:  98408, backward: 147632
\t\tRequest  98408, Owner:  78400, State: 6 (6), Flags: 0x00
\t\tRequest 147632, Owner:  99656, State: 0 (3), Flags: 0x02
"""

SAMPLE_INTERACTIVE = """
18:44:55 acquire/s acqwait/s  %acqwait enqueue/s
18:44:56        12         1         8         5

Average:        12         1         8         5
"""


def test_descriptor_never_publishes_default_metrics():
    desc = lp.descriptor()
    assert desc['schema'] == 'scratchrobin.firebird.lock-print-api@1'
    assert desc['published_as_default_metric'] is False
    assert desc['supported_platforms'] == ['linux']


def test_option_validation_enforces_cli_dependencies_and_raw_key_confirmation():
    opts = lp.normalize_options({'owners': True, 'locks': True, 'series': 4}, database_name='owned.fdb')
    assert lp.build_cli_arguments('/db/owned.fdb', opts) == ['-d', '/db/owned.fdb', '-c', '-o', '-l', '-w', '-s', '4']

    for invalid in (
        {'owners': False, 'requests': True},
        {'owners': False, 'waiting_only': True},
        {'owners': False, 'locks': False, 'pending_only': True},
        {'locks': False, 'series': 4},
        {'series': -1},
        {'interactive_seconds': 2, 'owners': True},
        {'interactive_seconds': 5, 'timeout_seconds': 5},
        {'interactive_counters': 'xyz'},
        {'include_raw_lock_keys': True},
        {'include_raw_lock_keys': True, 'sensitive_lock_data_confirmed': True, 'confirmation': 'wrong.fdb'},
        {'extra_field': 1},
    ):
        with pytest.raises(ValueError):
            lp.normalize_options(invalid, database_name='owned.fdb')

    confirmed = lp.normalize_options({
        'include_raw_lock_keys': True,
        'sensitive_lock_data_confirmed': True,
        'confirmation': 'owned.fdb',
    }, database_name='owned.fdb')
    assert confirmed['include_raw_lock_keys'] is True

    inter = lp.normalize_options({'interactive_seconds': 2, 'interactive_interval': 1, 'interactive_counters': 'ao'})
    assert lp.build_cli_arguments('/db/owned.fdb', inter) == ['-d', '/db/owned.fdb', '-iao', '2', '1']


def test_parser_extracts_header_waiting_owners_redacted_keys_and_strips_ast_pointers():
    parsed = lp.parse_lock_print_output(SAMPLE_SNAPSHOT, include_raw_keys=False)
    assert parsed['lock_table_state'] == 'active'
    assert parsed['header']['version'] == 147
    assert parsed['header']['blocks'] == 114
    assert parsed['header']['mutex_wait_percent'] == 8.8
    assert parsed['header']['owners_count'] == 2

    owner = parsed['owners'][0]
    assert owner['offset'] == 99656
    assert owner['pid'] == 1566401
    assert owner['pending_count'] == 1
    assert owner['waits_on_offsets'] == [78400]
    assert owner['is_waiting'] is True

    lock = parsed['locks'][0]
    assert lock['offset'] == 98480
    assert lock['series'] == 4
    assert lock['key'] == '[redacted]'
    assert lock['key_redacted'] is True
    assert len(lock['requests']) == 2
    assert lock['requests'][1]['owner_offset'] == 99656

    req = parsed['requests'][0]
    assert req['ast_pointers_redacted'] is True
    assert '7f3b2c8148c0' not in json.dumps(parsed)
    assert '7f3b2c8148c0' not in lp._sanitize_raw_text(SAMPLE_SNAPSHOT, include_raw_keys=True)

    raw_parsed = lp.parse_lock_print_output(SAMPLE_SNAPSHOT, include_raw_keys=True)
    assert raw_parsed['locks'][0]['key'] == '000000003'
    assert raw_parsed['locks'][0]['key_redacted'] is False


def test_parser_handles_unmapped_and_interactive_outputs():
    unmapped = lp.parse_lock_print_output('Unable to access lock table.\n', 'shmem_data->sh_mem_length_mapped is 0\n')
    assert unmapped['lock_table_state'] == 'unmapped_no_active_attachments'

    inter = lp.parse_lock_print_output(SAMPLE_INTERACTIVE)
    assert inter['lock_table_state'] == 'interactive_sampled'
    assert inter['interactive_samples'] == [{'time': '18:44:56', 'metrics': {'acquire/s': 12, 'acqwait/s': 1, '%acqwait': 8, 'enqueue/s': 5}}]
    assert inter['interactive_average'] == {'acquire/s': 12, 'acqwait/s': 1, '%acqwait': 8, 'enqueue/s': 5}


def test_journal_enforces_one_use_owner_isolation_and_persists_no_raw_output(tmp_path):
    store_path = tmp_path / 'lock-print.json'
    journal = LockPrintActions(store_path)
    rev = journal.review('alice', 'bind-1', {'options': {'owners': True}})
    with pytest.raises(ValueError):
        journal.get('bob', 'bind-1', rev['review_id'])

    applied = journal.apply(
        'alice', 'bind-1',
        {'review_id': rev['review_id'], 'review_digest': rev['review_digest'], 'confirmed': True},
        lambda _rec: {
            'state': 'completed',
            'native_dispatched': True,
            'timed_out': False,
            'process_cleaned_up': True,
            'return_code': 0,
            'parsed': lp.parse_lock_print_output(SAMPLE_SNAPSHOT, include_raw_keys=True),
            'sanitized_text': 'SECRET_KEY_MATERIAL_000000003',
        },
    )
    assert applied['durable_summary']['waiting_owners_observed'] == 1
    assert applied['durable_summary']['raw_output_persisted'] is False
    persisted_raw = store_path.read_text()
    assert '000000003' not in persisted_raw
    assert 'SECRET_KEY_MATERIAL' not in persisted_raw

    # Replay must be refused.
    with pytest.raises(ValueError, match='already consumed'):
        journal.apply(
            'alice', 'bind-1',
            {'review_id': rev['review_id'], 'review_digest': rev['review_digest'], 'confirmed': True},
            lambda _rec: {},
        )


def test_execute_lock_print_kills_timed_out_process_group(tmp_path):
    rt = tmp_path / 'fb5'
    (rt / 'bin').mkdir(parents=True)
    (rt / 'lib').mkdir(parents=True)
    (rt / 'lib/libfbclient.so.5.0.4').write_bytes(b'fbclient')
    hang_bin = rt / 'bin/fb_lock_print'
    hang_bin.write_text('#!/bin/sh\nsleep 30\n')
    hang_bin.chmod(0o755)
    db = tmp_path / 'owned.fdb'
    db.write_bytes(b'db')
    st = db.stat()
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    scope = {
        'attachment_mode': 'embedded',
        'platform': 'linux',
        'boot_id': boot_id,
        'hostname': 'local',
        'engine_version': '5.0.4',
        'binary_path': str(hang_bin),
        'binary_sha256': lp._file_sha256(hang_bin),
        'library_directory': str(rt / 'lib'),
        'firebird_runtime_root': str(rt),
        'firebird_lock_directory': '',
        'database': str(db),
        'database_identity': {'device': str(st.st_dev), 'inode': str(st.st_ino)},
        'grant_manifest_sha256': None,
    }
    opts = lp.normalize_options({'timeout_seconds': 1})
    res = lp.execute_lock_print(scope, opts)
    assert res['state'] == 'timed_out'
    assert res['timed_out'] is True
    assert res['process_cleaned_up'] is True
