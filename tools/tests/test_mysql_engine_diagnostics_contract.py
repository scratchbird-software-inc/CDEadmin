"""Qualification receipts cannot activate tasks after source/evidence drift."""
from copy import deepcopy
import hashlib

import pytest

from tools.reference_engine_demos.supplement_mysql_engine_diagnostics_contract import supplement


def receipt(tmp_path):
    names = ['web/pgadmin/cdeadmin/providers/mysql_family/' + name for name in (
        'mysql_engine_diagnostics.py', 'administration.py', 'provider.py')]
    hashes = {}
    for name in names:
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('qualified source\n'); hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    operations = ['show_engine_status', 'show_engine_logs', 'show_engine_mutex']
    templates = {operation: 'SHOW ENGINE `InnoDB` ' + operation.removeprefix('show_engine_').upper() for operation in operations}
    interfaces = []
    for pure in [True, False]:
        checks = [{'operation': operation, 'native_parser_accepted_by_execution': True, 'complete': True,
                   'connection_released': True, 'row_count': 1} for operation in operations]
        checks += [{'native_denied': operation, 'native_error_code': 1227,
                    'automatic_retry': False, 'connection_released': True} for operation in operations]
        interfaces.append({'use_pure': pure, 'native_connection_class': 'CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection',
                           'missing_engine_refused': True, 'checks': checks, 'templates': templates, 'all_checks': deepcopy(checks),
                           'all_templates': {operation: 'SHOW ENGINE ALL '+operation.removeprefix('show_engine_').upper()for operation in operations}})
    return {'complete': True, 'owned_server_stopped': True, 'native_version': '9.7.0',
            'interfaces': interfaces, 'source_sha256': hashes}


def contract():
    return {'engine_id': 'mysql', 'reference_version': '9.7.0', 'task_templates': [],
            'proof_records': [], 'live_evidence_ids': [], 'coverage': {}}


def test_qualified_task_receipt_cannot_be_reused_after_source_change(tmp_path):
    evidence = receipt(tmp_path)
    first = supplement(contract(), evidence, 'owned.json', 'a'*64, tmp_path)
    assert len(first['task_templates']) == 3
    (tmp_path/'web/pgadmin/cdeadmin/providers/mysql_family/provider.py').write_text('changed source\n')
    with pytest.raises(ValueError, match='source differs'):
        supplement(contract(), evidence, 'owned.json', 'a'*64, tmp_path)


@pytest.mark.parametrize('missing', ['complete', 'owned_server_stopped'])
def test_unfinished_or_unreleased_native_run_cannot_activate_dialect_tasks(tmp_path, missing):
    evidence = receipt(tmp_path); evidence[missing] = False
    with pytest.raises(ValueError): supplement(contract(), evidence, 'owned.json', 'a'*64, tmp_path)


def test_receipt_must_not_replace_denial_or_complete_native_results_with_empty_success(tmp_path):
    evidence = receipt(tmp_path)
    for change in ['denial', 'result']:
        altered = deepcopy(evidence)
        if change == 'denial': altered['interfaces'][1]['checks'].pop()
        else: altered['interfaces'][0]['checks'][0]['complete'] = False
        with pytest.raises(ValueError): supplement(contract(), altered, 'owned.json', 'a'*64, tmp_path)


def test_single_engine_receipt_cannot_activate_all_engine_scope(tmp_path):
    evidence=receipt(tmp_path);evidence['interfaces'][0].pop('all_checks')
    with pytest.raises(ValueError,match='ALL-engine'):
        supplement(contract(),evidence,'owned.json','a'*64,tmp_path)
