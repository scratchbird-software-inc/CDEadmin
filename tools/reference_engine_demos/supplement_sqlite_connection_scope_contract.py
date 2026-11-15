"""Admit the corrected file-only database-alter task from fresh native receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def supplement(receipt, contract):
    proof = json.loads(receipt.read_text())
    if (proof.get('complete') is not True or
            {row['version'] for row in proof.get('versions', [])} != {'3.35.0', '3.45.1', '3.53.0'} or
            any(row['exit_code'] != 0 for row in proof['versions'])):
        raise ValueError('Three current native SQLite version receipts are required')
    for name, digest in proof['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Native receipt source changed: ' + name)
    for row in proof['versions']:
        suites = ET.parse(receipt.parent / ('five-sqlite-' + row['version'] + '.xml')).getroot().findall('.//testsuite')
        if (sum(int(suite.get('tests', 0)) for suite in suites) < 10 or
                any(int(suite.get(key, 0)) for suite in suites for key in ['failures', 'errors', 'skipped'])):
            raise ValueError('Native file-property and connection-scope tests must all pass')
    value = json.loads(contract.read_text())
    if value.get('engine_id') != 'sqlite' or value.get('reference_version') != '3.53.0':
        raise ValueError('Select the SQLite reference contract')
    manifest = {'scope': 'database.alter file task excludes connection-local synchronous; original main connection policy is a separate retained callback',
        'native_versions': [row['version'] for row in proof['versions']],
        'source_sha256': proof['source_sha256'],
        'statements': ['PRAGMA journal_mode = DELETE', 'PRAGMA user_version = 53']}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    value['connection_scope_qualification'] = manifest
    identifiers = []
    for kind in ['parser_acceptance', 'live_execution']:
        identifier = 'sqlite-connection-scope-' + kind
        identifiers.append(identifier)
        value['proof_records'] = [row for row in value['proof_records'] if row['evidence_id'] != identifier]
        value['proof_records'].append({'evidence_id': identifier, 'evidence_kind': kind,
            'authority': 'Owned native three-runtime file-setting apply/read-back and retained-setting scope tests',
            'artifact': 'embedded connection_scope_qualification', 'sha256': digest,
            'format': 'scoped native qualification manifest', 'license_id': 'PostgreSQL'})
    for task in value['task_templates']:
        if task['task_id'] == 'visual_admin.database.alter':
            task.update(source='\n;\n'.join(manifest['statements']), statements=manifest['statements'], proof_ids=identifiers)
    value['live_evidence_ids'] = sorted(set(value['live_evidence_ids']) | {identifiers[1]})
    contract.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    supplement(args.receipt, ROOT / 'web/pgadmin/cdeadmin/providers/sqlite/sqlite_dialect_3_53_0.json')
