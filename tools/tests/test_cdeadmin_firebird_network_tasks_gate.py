"""A passing partial receipt must never close missing native task coverage."""

from copy import deepcopy

import pytest

from tools.cdeadmin_firebird_network_tasks_gate import (
    declared_tasks, qualified_tasks, task_evidence,
)


def generic():
    return {
        'engine_id': 'firebird', 'exact_profile': '5.0.4',
        'server_stopped': True, 'source_runtime_modified': False,
        'error_type': None, 'object_experience_evidence': {
            'operation_failures': {}},
        'categories': {key: 'passed' for key in (
            'admin', 'fault', 'language_api', 'resource', 'result',
            'security', 'transaction')},
        'qualified_dialect_task_ids': ['visual_admin.table.create'],
    }


def test_partial_generic_proof_retains_only_exercised_tasks():
    tasks = qualified_tasks('generic', generic(), 1)
    assert tasks == {'visual_admin.table.create'}
    assert tasks < declared_tasks()


@pytest.mark.parametrize('field,value', [
    ('server_stopped', False), ('source_runtime_modified', True),
    ('exact_profile', '5.0.3'), ('engine_id', 'firebird-embedded'),
    ('error_type', 'NativeFailure'), ('categories', {}),
    ('object_experience_evidence', {'operation_failures': {'table': 'failed'}}),
])
def test_generic_failure_cannot_contribute_task_coverage(field, value):
    receipt = generic()
    receipt[field] = value
    assert qualified_tasks('generic', receipt, 1) is None


def specialized():
    return {
        'engine_version': '5.0.4', 'complete': True, 'failures': [],
        'function_task_evidence': {
            'visual_admin.function.recreate': {'live_execution': 'passed'},
            'visual_admin.function.create_or_alter': {
                'live_execution': 'failed'},
        },
        'sql': 'visual_admin.table.recreate',
    }


def test_specialized_receipt_uses_explicit_successful_native_evidence():
    assert task_evidence(specialized()) == {'visual_admin.function.recreate'}
    assert qualified_tasks('functions', specialized(), 0) == {
        'visual_admin.function.recreate'}


@pytest.mark.parametrize('change,exit_code', [
    ({'complete': False}, 0), ({'engine_version': '5.0.3'}, 0),
    ({'failures': [{'case': 'rollback'}]}, 0), ({}, 1),
])
def test_failed_specialized_gate_contributes_no_tasks(change, exit_code):
    receipt = deepcopy(specialized())
    receipt.update(change)
    assert qualified_tasks('functions', receipt, exit_code) is None
