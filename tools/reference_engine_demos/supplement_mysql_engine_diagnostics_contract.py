"""Admit exact engine diagnostic tasks after native execution on both drivers."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPERATIONS = {'show_engine_status', 'show_engine_logs', 'show_engine_mutex'}
PROOFS = ['mysql-9.7.0-engine-diagnostics-parser', 'mysql-9.7.0-engine-diagnostics-execution']


def supplement(contract, evidence, artifact, digest, source_root):
    if (evidence.get('complete') is not True or evidence.get('owned_server_stopped') is not True
            or evidence.get('native_version') != '9.7.0'):
        raise ValueError('Completed exact native execution and owned fixture cleanup are required')
    interfaces = evidence.get('interfaces', [])
    if len(interfaces) != 2 or {row.get('use_pure') for row in interfaces} != {True, False}:
        raise ValueError('Both native MySQL driver implementations are required')
    templates = None
    for interface in interfaces:
        expected_class = 'CharsetMySQLConnection' if interface['use_pure'] else 'CharsetCMySQLConnection'
        if interface.get('native_connection_class') != expected_class or interface.get('missing_engine_refused') is not True:
            raise ValueError('Exact native driver and installed-engine refusal evidence are required')
        rows = interface.get('checks', [])
        passed = {row['operation']: row for row in rows if 'operation' in row}
        denied = {row['native_denied']: row for row in rows if 'native_denied' in row}
        if len(rows) != 6 or set(passed) != OPERATIONS or set(denied) != OPERATIONS:
            raise ValueError('Every operation needs native execution and native permission refusal')
        for operation, result in passed.items():
            if (result.get('native_parser_accepted_by_execution') is not True
                    or result.get('complete') is not True or result.get('connection_released') is not True
                    or operation == 'show_engine_status' and result.get('row_count', 0) < 1):
                raise ValueError('Complete native results and cleanup are required')
        if any(row.get('native_error_code') not in {1044, 1045, 1142, 1227}
               or row.get('automatic_retry') is not False or row.get('connection_released') is not True
               for row in denied.values()):
            raise ValueError('Native refusal and cleanup evidence are required')
        selected = interface.get('templates')
        expected = {'show_engine_' + suffix.lower(): 'SHOW ENGINE `InnoDB` ' + suffix
                    for suffix in ('STATUS', 'LOGS', 'MUTEX')}
        if selected != expected or templates is not None and templates != selected:
            raise ValueError('Exact native diagnostic statements must agree on both drivers')
        templates = selected
        expected_all = {operation: 'SHOW ENGINE ALL ' + operation.removeprefix('show_engine_').upper()
                        for operation in OPERATIONS}
        if interface.get('all_templates') != expected_all:
            raise ValueError('Native ALL-engine statements are required')
        all_rows = interface.get('all_checks', [])
        all_passed = {row['operation']: row for row in all_rows if 'operation' in row}
        all_denied = {row['native_denied']: row for row in all_rows if 'native_denied' in row}
        if len(all_rows) != 6 or set(all_passed) != OPERATIONS or set(all_denied) != OPERATIONS:
            raise ValueError('Every ALL-engine operation needs native execution and permission refusal')
        if any(row.get('complete') is not True or row.get('connection_released') is not True or
               row.get('native_parser_accepted_by_execution') is not True for row in all_passed.values()):
            raise ValueError('Complete ALL-engine execution and cleanup are required')
        if any(row.get('native_error_code') not in {1044,1045,1142,1227} or
               row.get('automatic_retry') is not False or row.get('connection_released') is not True
               for row in all_denied.values()):
            raise ValueError('ALL-engine native refusal and cleanup are required')
    required = {'web/pgadmin/cdeadmin/providers/mysql_family/' + name
                for name in ('mysql_engine_diagnostics.py', 'administration.py', 'provider.py')}
    if not required <= set(evidence.get('source_sha256', {})):
        raise ValueError('Implementation source fingerprints are required')
    for name, digest_value in evidence['source_sha256'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or hashlib.sha256((source_root/path).read_bytes()).hexdigest() != digest_value:
            raise ValueError('Native execution source differs: ' + name)
    if contract.get('engine_id') != 'mysql' or contract.get('reference_version') != '9.7.0':
        raise ValueError('Select the exact MySQL 9.7.0 contract')
    result = deepcopy(contract)
    ids = {'visual_admin.server.' + operation for operation in OPERATIONS}
    result['task_templates'] = [row for row in result['task_templates'] if row['task_id'] not in ids]
    result['task_templates'] += [{'task_id': 'visual_admin.server.' + operation,
        'source': source, 'proof_ids': PROOFS} for operation, source in sorted(templates.items())]
    result['task_templates'].sort(key=lambda row: row['task_id'])
    result['proof_records'] = [row for row in result['proof_records'] if row['evidence_id'] not in PROOFS]
    for proof, kind in zip(PROOFS, ('parser_acceptance', 'live_execution')):
        result['proof_records'].append({'evidence_id': proof, 'evidence_kind': kind,
            'artifact': artifact, 'sha256': digest, 'license_id': 'PostgreSQL',
            'authority': 'Owned native MySQL 9.7.0 pure/C execution: exact SHOW ENGINE statements, native permission/installed-engine refusals and cleanup; HTTP qualification is separate',
            'format': 'native engine diagnostic qualification JSON; parser acceptance established by successful native execution, not nonexecuting PREPARE'})
    result['live_evidence_ids'] = sorted(set(result['live_evidence_ids']) | {PROOFS[1]})
    tasks = [row['task_id'] for row in result['task_templates']]
    result['coverage'].update(authoritative_task_ids=tasks, authoritative_task_count=len(tasks), implemented_task_count=len(tasks))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--contract', type=Path, default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args = parser.parse_args(); raw = args.evidence.read_bytes()
    result = supplement(json.loads(args.contract.read_text()), json.loads(raw), args.evidence.name,
                        hashlib.sha256(raw).hexdigest(), ROOT)
    args.contract.write_text(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
