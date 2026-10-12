"""Embedded activation keeps profile identity and proof boundaries intact."""

import copy
import json

import pytest

from tools.reference_engine_demos.generate_firebird_embedded_contracts import (
    PACKAGE, generate,
)
from pgadmin.cdeadmin.engine_contracts import (
    EngineContractError, contract_descriptor, validate_dialect_contract,
)
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird import provider as network


def documents():
    return tuple(json.loads((PACKAGE / name).read_text()) for name in (
        embedded.PROFILE.dialect_contract_file,
        embedded.PROFILE.metrics_contract_file))


def test_embedded_uses_own_identity_without_relaxing_network_validation():
    descriptor = contract_descriptor(
        embedded.PROFILE, embedded.__name__,
        embedded.ADMINISTRATION.dialect_task_ids())
    assert descriptor['state'] == 'passed'
    assert descriptor['profile_id'] == 'firebird-embedded'
    dialect, _metrics = documents()
    with pytest.raises(EngineContractError, match='provider_id'):
        validate_dialect_contract(dialect, network.PROFILE)
    native = json.loads((PACKAGE /
                         network.PROFILE.dialect_contract_file).read_text())
    with pytest.raises(EngineContractError, match='provider_id'):
        validate_dialect_contract(native, embedded.PROFILE)
    assert dialect['task_templates'] == native['task_templates']
    assert dialect['proof_records'] == native['proof_records']


def test_generated_artifacts_match_current_native_receipt_and_compiler():
    dialect, metrics = documents()
    proof = dialect['embedded_attachment_evidence']
    assert generate(proof['receipt'], proof['sha256']) == (dialect, metrics)
    assert all(item['source'].startswith('MON$')
               for item in metrics['native_observations'])
    assert not any('server-info' in item['evidence_id']
                   for item in metrics['classification_evidence'])
    assert metrics['authoritative_observation_count'] == len(
        metrics['embedded_attachment_evidence']['receipt'][
            'monitoring_observation_ids'])


@pytest.mark.parametrize('key,value', [
    ('complete', False), ('engine_version', '3.0.0'),
    ('remote_protocol_absent', False), ('source_runtime_unchanged', False),
    ('source_bindings', {}), ('monitoring_observation_ids', []),
    ('task_ids', []), ('transaction_observations', []),
])
def test_incomplete_or_stale_native_receipt_cannot_activate(key, value):
    dialect, _ = documents()
    proof = dialect['embedded_attachment_evidence']
    receipt = copy.deepcopy(proof['receipt'])
    receipt[key] = value
    with pytest.raises(ValueError):
        generate(receipt, proof['sha256'])


def test_new_embedded_compiler_override_requires_separate_proof(monkeypatch):
    dialect, _ = documents()
    proof = dialect['embedded_attachment_evidence']
    monkeypatch.setattr(embedded.EmbeddedAdministration, 'plan',
                        lambda *_: None)
    with pytest.raises(ValueError, match='equivalence'):
        generate(proof['receipt'], proof['sha256'])
