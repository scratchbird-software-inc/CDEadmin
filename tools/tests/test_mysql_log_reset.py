"""Native reset intent, exact state binding and non-replaying receipts."""
from copy import deepcopy
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_log_reset as native
from pgadmin.cdeadmin.workspace.mysql_log_reset import ResetJobs
from test_mysql_log_purge import captured, finish, Transport


@pytest.mark.parametrize('value', [None, {'to_sequence': 0}, {'to_sequence': 2000000001},
    {'to_sequence': True}, {'to_sequence': '1'}, {'to_sequence': 1.5},
    {'timeout_seconds': 0}, {'timeout_seconds': True}, {'to_file': 'a'}, {'route': {}}])
def test_reset_cannot_accept_purge_options_or_non_native_sequence(value):
    with pytest.raises(native.BinlogArchiveError): native.options(value)


def test_reset_binds_full_native_observation_and_retains_native_default_and_maximum():
    source = captured()
    selected = native.options({})
    transport = native.Transport(None, None, None, source, selected)
    assert transport.statement({'options': selected}) == ('RESET BINARY LOGS AND GTIDS', ())
    maximum = native.options({'to_sequence': 2000000000})
    assert transport.statement({'options': maximum}) == ('RESET BINARY LOGS AND GTIDS TO %s', (2000000000,))
    before = native.selection(None, source, selected)
    for key in ('gtid_executed', 'gtid_purged', 'gtid_mode'):
        after = deepcopy(source); after['state'][key] += 'changed'
        assert native.selection(None, after, selected) != before
    assert before['candidate_selection'] == 'all-native-binary-logs-and-gtid-history'
    disabled = deepcopy(source); disabled.update(status='native_binary_logging_disabled', logs=[], current=None)
    assert native.selection(None, disabled, selected)['before_state']['gtid_executed']


def test_reset_reconciliation_keeps_unknown_even_when_filenames_are_reused(tmp_path):
    source = captured(); selected = native.options({})
    source['state']['reset_selection'] = native.selection(None, source, selected)
    jobs = ResetJobs(tmp_path / 'jobs.json', tmp_path / 'receipts'); endpoint = str(uuid.uuid4())
    try:
        program = native.program(source)
        review = jobs.review(1, endpoint, selected, source, 'registration', program)
        assert review['reset_selection']['before_logs'][0]['File_size'] == '9007199254740993'
        request = {**{key: review[key] for key in ('job_id', 'review_digest')}, 'confirmed': True}
        transport = Transport(fault=True)
        jobs.start(request, 1, endpoint, {'source': source['identity'], 'configuration': 'registration', 'program': program}, transport)
        assert finish(jobs, endpoint, review)['state'] == 'unknown'
        observed = captured(); observed['identity'] = source['identity']; observed['state'].update(gtid_executed='', gtid_purged='')
        result = jobs.reconcile_source(jobs.load(review['job_id'], 1, endpoint), observed)
        assert result['state'] == 'unknown' and not result['reconciliation']['native_log_generation_attested']
        assert result['reconciliation']['filename_reuse_does_not_identify_original_log_files']
        assert 'absent_before_names' not in result['reconciliation']
        assert jobs.start(request, 1, endpoint, {}, None)['state'] == 'unknown' and transport.calls == 1
        assert result['operation'] == 'mysql_native_binary_logs_and_gtids_reset'
    finally:
        assert jobs.close()


def test_reset_cannot_turn_gtid_observations_into_a_native_acknowledgement():
    observed = captured(); observed['state'].update(gtid_executed='', gtid_purged='')
    transport = native.Transport(None, None, None, observed, {})
    result = transport.postconditions({'options': {'to_sequence': None}}, observed)
    assert result['gtid_executed_empty_observed'] and result['gtid_purged_empty_observed']
    assert not result['native_log_generation_attested'] and 'native_acknowledged' not in result
