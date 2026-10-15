"""Bind the shared Firebird SQL dialect to a qualified local profile.

Shared statement proofs retain their original IDs and scope. The separate
embedded receipt proves attachment and monitoring behavior; it does not claim
that every statement was executed again over every attachment mode/platform.
"""

import argparse
import copy
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import re

from tools.cdeadmin_firebird_embedded_contract_gate import (
    PACKAGE, source_bindings,
)
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird import provider as network
from pgadmin.cdeadmin.providers.relational_admin import (
    RelationalAdministration,
)
from pgadmin.cdeadmin.engine_contracts import (
    validate_dialect_contract, validate_metrics_contract,
)


def generate(receipt, receipt_digest):
    """Reject stale/incomplete evidence and divergent compiler semantics."""
    if not isinstance(receipt_digest, str) or not re.fullmatch(
            '[0-9a-f]{64}', receipt_digest):
        raise ValueError('Native evidence requires a SHA-256 digest')
    required = ('complete', 'attachment_in_current_process',
                'remote_protocol_absent', 'provider_compiled_create',
                'all_client_handles_released', 'owned_state_removed',
                'source_runtime_unchanged')
    if (receipt.get('schema') !=
            'cdeadmin.firebird-embedded-contract-proof.v1' or
            any(receipt.get(key) is not True for key in required) or
            receipt.get('engine_version') != embedded.PROFILE.exact_version or
            receipt.get('failures') != [] or
            receipt.get('source_bindings') != source_bindings() or
            receipt.get('transaction_observations') != [
                {'commit': False, 'rows': 0}, {'commit': True, 'rows': 1}]):
        raise ValueError(
            'Current complete native embedded evidence is required')
    local = embedded.ADMINISTRATION
    shared = network.ADMINISTRATION
    if (type(shared) is not RelationalAdministration or
            set(vars(type(local))).difference({
                '__module__', '__doc__', '__firstlineno__',
                '__static_attributes__', 'catalog'}) or
            local.dialect_task_ids() != shared.dialect_task_ids() or
            receipt.get('task_ids') != list(local.dialect_task_ids())):
        raise ValueError(
            'Embedded SQL compiler equivalence is not established')
    for field in fields(shared.dialect):
        if field.name not in {'supported', 'not_applicable_concepts'} and (
                getattr(local.dialect, field.name) !=
                getattr(shared.dialect, field.name)):
            raise ValueError('Embedded dialect differs: ' + field.name)
    dialect = json.loads((PACKAGE /
                          network.PROFILE.dialect_contract_file).read_text())
    metrics = json.loads((PACKAGE /
                          network.PROFILE.metrics_contract_file).read_text())
    validate_dialect_contract(dialect, network.PROFILE,
                              shared.dialect_task_ids())
    validate_metrics_contract(metrics, network.PROFILE)
    observations = [item for item in metrics['native_observations']
                    if item['source'].startswith('MON$')]
    observation_ids = sorted(item['observation_id'] for item in observations)
    if receipt.get('monitoring_observation_ids') != observation_ids:
        raise ValueError('Embedded monitoring evidence is incomplete')
    metrics['native_observations'] = observations
    metrics['authoritative_observation_ids'] = observation_ids
    metrics['authoritative_observation_count'] = len(observations)
    metrics['metrics'] = [item for item in metrics['metrics']
                          if item['observation_id'] in observation_ids]
    metrics['authoritative_metric_ids'] = sorted(
        item['metric_id'] for item in metrics['metrics'])
    metrics['authoritative_metric_count'] = len(metrics['metrics'])
    needed = {key for item in observations + metrics['metrics']
              for key in item['evidence_ids']}
    metrics['classification_evidence'] = [
        item for item in metrics['classification_evidence']
        if item['evidence_id'] in needed]
    metrics['live_evidence_ids'] = ['firebird-5.0.4-embedded-metrics']
    for kind, document in (('dialect', dialect), ('metrics', metrics)):
        document.update(
            provider_id=embedded.PROFILE.provider_id,
            profile_id=embedded.PROFILE.profile_id,
            interface_id='firebird-embedded',
            contract_id=f'firebird.embedded.{kind}.5.0.4.v2',
            shared_evidence_scope={
                'source_profile': network.PROFILE.profile_id,
                'scope': ('Unchanged exact-engine SQL compiler and grammar; '
                          'MON$ definitions and classification. No network, '
                          'service or cross-platform qualification transfer.'),
                'source_bindings': copy.deepcopy(receipt['source_bindings'])},
            embedded_attachment_evidence={
                'evidence_id': 'firebird-5.0.4-embedded-' + kind,
                'artifact': f'firebird-embedded-contract/{receipt_digest}/summary.json',
                'sha256': receipt_digest,
                'scope': ('Engine13 local attachment, provider-compiled table '
                          'creation, independent transaction visibility and '
                          'declared monitoring columns. Not exhaustive '
                          'per-task or product qualification.'),
                'receipt': copy.deepcopy(receipt)})
    validate_dialect_contract(dialect, embedded.PROFILE,
                              local.dialect_task_ids())
    validate_metrics_contract(metrics, embedded.PROFILE)
    return dialect, metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-evidence', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    raw = args.native_evidence.read_bytes()
    documents = generate(json.loads(raw), hashlib.sha256(raw).hexdigest())
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for name, document in zip((embedded.PROFILE.dialect_contract_file,
                               embedded.PROFILE.metrics_contract_file),
                              documents):
        (args.output_directory / name).write_text(
            json.dumps(document, indent=2, sort_keys=True) + '\n')
