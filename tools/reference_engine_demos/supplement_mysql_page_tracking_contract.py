"""Admit native page-tracking statements after independent pure/C core execution."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPERATIONS = {'inspect_page_tracking', 'start_page_tracking', 'stop_page_tracking', 'count_tracked_pages', 'set_page_tracking_backup_id', 'export_tracked_pages', 'purge_page_tracking'}
PROOFS = ['mysql-9.7.0-page-tracking-parser', 'mysql-9.7.0-page-tracking-execution']


def supplement(contract, evidence, artifact, digest, source_root):
    if not evidence.get('core_complete') or not evidence.get('owned_server_stopped'):
        raise ValueError('Completed core page-tracking execution and stopped owned fixture are required')
    interfaces = evidence.get('interfaces', [])
    if len(interfaces) != 2 or {row.get('use_pure') for row in interfaces} != {True, False}:
        raise ValueError('Both native drivers are required')
    templates = None
    for row in interfaces:
        if row.get('native_connection_class') != ('CharsetMySQLConnection' if row['use_pure'] else 'CharsetCMySQLConnection') or len(row.get('checks', [])) != 5 or set(row.get('templates', {})) != OPERATIONS:
            raise ValueError('Native page-tracking operations, native return codes and transaction preservation are required')
        checks = {item['scope']: item for item in row['checks']}
        if set(checks) != {'native-active-window-count-and-export', 'native-nonexception-failures-and-prior-index-removal', 'native-null-and-default-backup-id', 'changed-input-refusal-and-post-ack-loss', 'native-stop-purge-and-independent-pending-transaction'}: raise ValueError('Required native interface checks are absent')
        file = checks['native-active-window-count-and-export']
        if file['independent_fixture_file_bytes'] != int(file['native_count']) * 8 or int(file['native_count']) <= 0: raise ValueError('Native index/count evidence differs')
        failures = checks['native-nonexception-failures-and-prior-index-removal']
        if (failures['duplicate_status'], failures['count_status'], failures['export_status'], failures['prior_native_index_removed']) != ('-1', '-3803', '3803', True): raise ValueError('Native failure/deletion semantics are absent')
        if not checks['native-stop-purge-and-independent-pending-transaction']['savepoint_preserved']: raise ValueError('Pending native work was not preserved')
        if templates is not None and row['templates'] != templates: raise ValueError('Driver statements differ')
        templates = row['templates']
    required = {'web/pgadmin/cdeadmin/providers/mysql_family/' + name for name in ('mysql_page_tracking.py', 'administration.py', 'provider.py')}
    if not required <= set(evidence.get('source_sha256', {})): raise ValueError('Native source fingerprints are required')
    for name, value in evidence['source_sha256'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or hashlib.sha256((source_root / path).read_bytes()).hexdigest() != value:
            raise ValueError('Native page-tracking source differs: ' + name)
    result = deepcopy(contract)
    if result.get('engine_id') != 'mysql' or result.get('reference_version') != '9.7.0': raise ValueError('Select MySQL 9.7.0')
    ids = {'visual_admin.server.' + operation for operation in OPERATIONS}
    result['task_templates'] = [row for row in result['task_templates'] if row['task_id'] not in ids]
    for operation, source in sorted(templates.items()):
        bindings = ['start_lsn', 'stop_lsn'] if operation in {'count_tracked_pages', 'export_tracked_pages'} else ['backup_id'] if operation == 'set_page_tracking_backup_id' else ['purge_lsn'] if operation == 'purge_page_tracking' else []
        result['task_templates'].append({'task_id': 'visual_admin.server.' + operation, 'source': source,
            'source_format': 'ordered_native_statements', 'statements': [source], 'required_bindings': bindings,
            'binding_style': 'pyformat_percent_s', 'proof_ids': PROOFS})
    result['task_templates'].sort(key=lambda row: row['task_id'])
    result['proof_records'] = [row for row in result['proof_records'] if row['evidence_id'] not in PROOFS]
    for proof, kind in zip(PROOFS, ('parser_acceptance', 'live_execution')):
        result['proof_records'].append({'evidence_id': proof, 'evidence_kind': kind,
            'authority': 'Actual native MySQL 9.7 page-tracking core execution with independent pure/C drivers and independent native file/count observations; API/browser status is separate',
            'artifact': artifact, 'sha256': digest, 'format': 'native page-tracking core qualification JSON', 'license_id': 'PostgreSQL'})
    result['live_evidence_ids'] = sorted(set(result['live_evidence_ids']) | {PROOFS[1]})
    tasks = [row['task_id'] for row in result['task_templates']]
    result['coverage'].update(authoritative_task_ids=tasks, authoritative_task_count=len(tasks), implemented_task_count=len(tasks))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--contract', type=Path, default=ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args = parser.parse_args(); raw = args.evidence.read_bytes()
    result = supplement(json.loads(args.contract.read_text()), json.loads(raw), args.evidence.name, hashlib.sha256(raw).hexdigest(), ROOT)
    args.contract.write_text(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
