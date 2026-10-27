"""Native MySQL reset of binary logs and GTID history, never a purge alias."""
from copy import deepcopy
import hashlib
from pathlib import Path

from . import mysql_log_purge as purge
from .mysql_binlog_archives import BinlogArchiveError, capture

private_connection = purge.private_connection


def options(value):
    if not isinstance(value, dict) or set(value) - {'to_sequence', 'timeout_seconds'}:
        raise BinlogArchiveError('Select a native binary-log reset request')
    sequence = value.get('to_sequence')
    if sequence is not None and (type(sequence) is not int or not 1 <= sequence <= 2000000000):
        raise BinlogArchiveError('Select a native log sequence from 1 through 2000000000 or null for the server default')
    timeout = value.get('timeout_seconds', 60)
    if timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise BinlogArchiveError('Select positive client read-timeout seconds or null')
    return {'to_sequence': sequence, 'timeout_seconds': timeout}


def selection(_connection, observed, _selected):
    if observed['status'] == 'available':
        before_names = purge.names(observed)
    elif observed['status'] == 'native_binary_logging_disabled':
        before_names = []
    else:
        raise BinlogArchiveError('Native binary-log reset state is unavailable')
    # Reset destroys a generation, including GTID history. Require an unchanged
    # observation, rather than allowing the forward GTID growth used by purge.
    return {'before_names': before_names, 'before_state': deepcopy(observed['state']),
            'before_logs': deepcopy(observed['logs']), 'before_current': deepcopy(observed['current']),
            'candidate_selection': 'all-native-binary-logs-and-gtid-history',
            'requires_unchanged_observation': True, 'native_generation_attested': False}


def program(observed):
    return {**purge.program(observed),
            'reset_adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class Transport(purge.Transport):
    selection_key = 'reset_selection'
    command_prefix = 'RESET BINARY LOGS AND GTIDS'

    def validate(self, record):
        current = capture(self.worker)
        if current['identity'] != record['source'] or selection(self.worker, current, record['options']) != record['source_state'][self.selection_key]:
            raise BinlogArchiveError('Native log or GTID state changed; prepare a new reset review in an exclusive maintenance window')

    def statement(self, record):
        sequence = record['options']['to_sequence']
        if sequence is None:
            return 'RESET BINARY LOGS AND GTIDS', ()
        return 'RESET BINARY LOGS AND GTIDS TO %s', (sequence,)

    def postconditions(self, record, after):
        return {'after': after,
                'gtid_executed_empty_observed': after['state']['gtid_executed'] == '',
                'gtid_purged_empty_observed': after['state']['gtid_purged'] == '',
                'expected_initial_sequence': str(record['options']['to_sequence'] or 1),
                'native_log_generation_attested': False,
                'filename_reuse_does_not_identify_original_log_files': True}
