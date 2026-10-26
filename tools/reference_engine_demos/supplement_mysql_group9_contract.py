"""Admit retained-session tasks only from matching native pure/C evidence."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def supplement(contract, evidence, artifact, digest, root):
    if not evidence.get('complete') or not evidence.get('owned_servers_stopped'):
        raise ValueError('Completed, cleaned native qualification is required')
    interfaces = evidence.get('interfaces', [])
    if {row.get('native_connection_class') for row in interfaces} != {'CharsetMySQLConnection', 'CharsetCMySQLConnection'}:
        raise ValueError('Both native connectors are required')
    required = ('temporary_lifecycle_and_savepoint', 'explicit_roles_and_temp_shadow', 'foreign_key_actions',
        'unenforced_check', 'protected_target_failover_and_pool_reset', 'disabled_instrumentation_and_pool_lifetime')
    if len(interfaces) != 2 or not all(row.get(key) for row in interfaces for key in required):
        raise ValueError('Native effects and independent lifecycle proof are incomplete')
    if evidence.get('parser', {}).get('parser_version') != '9.7.0' or not evidence['parser'].get('library_sha256'):
        raise ValueError('Native parser proof is required')
    for path, expected in evidence['source_sha256'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest() != expected:
            raise ValueError('Qualified source changed: ' + path)
    value = deepcopy(contract)
    proof_ids = ['mysql-9.7.0-retained-tasks-parser', 'mysql-9.7.0-retained-tasks-execution']
    for operation, kind in [('refresh_session_metadata', 'server'), ('drop_temporary', 'table')]:
        source = interfaces[0]['templates'][operation]
        if any(row['templates'][operation] != source for row in interfaces):
            raise ValueError('Native statement templates differ')
        task_id = 'visual_admin.' + kind + '.' + operation
        value['task_templates'] = [row for row in value['task_templates'] if row['task_id'] != task_id]
        value['task_templates'].append({'task_id': task_id, 'source': source, 'proof_ids': proof_ids})
    value['task_templates'].sort(key=lambda row: row['task_id'])
    value['proof_records'] = [row for row in value['proof_records'] if row['evidence_id'] not in proof_ids] + [
        {'evidence_id': proof_id, 'evidence_kind': kind, 'authority': 'Native MySQL9.7 Community retained sessions, pure/C and disabled instrumentation',
         'artifact': artifact, 'sha256': digest, 'format': 'Native retained-session qualification JSON', 'license_id': 'PostgreSQL'}
        for proof_id, kind in zip(proof_ids, ['parser_acceptance', 'live_execution'])]
    value['live_evidence_ids'] = sorted(set(value['live_evidence_ids']) | {proof_ids[1]})
    tasks = [row['task_id'] for row in value['task_templates']]
    value['coverage'].update(authoritative_task_ids=tasks, authoritative_task_count=len(tasks), implemented_task_count=len(tasks))
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--contract', type=Path, default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args = parser.parse_args()
    raw = args.evidence.read_bytes()
    value = supplement(json.loads(args.contract.read_text()), json.loads(raw), args.evidence.name, hashlib.sha256(raw).hexdigest(), ROOT)
    args.contract.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n')
