"""Record native corrected C attribute evidence without changing task coverage."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROOFS = ('mysql-connector-python-26.7.0-c-attributes', 'mysql-9.7.0-c-attributes-execution')


def supplement(contract, evidence, artifact, digest, root):
    if contract.get('engine_id') != 'mysql' or contract.get('reference_version') != '9.7.0':
        raise ValueError('Select the MySQL 9.7.0 contract')
    interfaces = evidence.get('interfaces', [])
    if not evidence.get('complete') or len(interfaces) != 2 or {item.get('use_c') for item in interfaces} != {True, False}:
        raise ValueError('Completed independent native pure/C receipts are required')
    for item in interfaces:
        expected = 'CharsetCMySQLConnection' if item['use_c'] else 'CharsetMySQLConnection'
        if (not item.get('complete') or not item.get('owned_server_stopped') or item.get('native_connection_class') != expected or
                len(item.get('checks', [])) != 4 or not item.get('application', {}).get('complete')):
            raise ValueError('Native runtime and authenticated application receipts are incomplete')
    native = next(item for item in interfaces if item['use_c'])
    browser = native['application'].get('browser', {})
    if native.get('native_query_attributes_abi') != 1 or not browser.get('complete') or len(browser.get('checks', [])) != 3 or browser.get('console_errors'):
        raise ValueError('Corrected native ABI and completed desktop evidence are required')
    build = evidence['build']
    if (build.get('source_sha256') != 'd8ff5ee236ea46661ee639336323e124ed868e37f3ea991bdc5de5a146f39fd5' or
            native['native_extension_sha256'] != evidence['wheel_extension_sha256']):
        raise ValueError('The native runtime differs from the source-built wheel')
    for name, value in evidence['source_sha256'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or hashlib.sha256((root/path).read_bytes()).hexdigest() != value:
            raise ValueError('Native implementation source differs: '+name)
    patch = 'tools/driver_patches/mysql-connector-python-26.7.0-query-attributes.patch'
    if build['patch_sha256'] != evidence['source_sha256'][patch]:
        raise ValueError('The compiled native patch differs')
    result = deepcopy(contract)
    result['proof_records'] = [item for item in result['proof_records'] if item['evidence_id'] not in PROOFS]
    for proof, kind in zip(PROOFS, ('driver', 'live_execution')):
        result['proof_records'].append({'evidence_id': proof, 'evidence_kind': kind,
            'authority': 'Pinned official Connector/Python source with corrected native C bindings; actual MySQL9.7 pure/C/API/desktop',
            'artifact': artifact, 'sha256': digest, 'format': 'owned native driver and runtime qualification JSON', 'license_id': 'PostgreSQL'})
    result['live_evidence_ids'] = sorted(set(result['live_evidence_ids']) | {PROOFS[1]})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--contract', type=Path, default=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json')
    args = parser.parse_args(); raw = args.evidence.read_bytes()
    result = supplement(json.loads(args.contract.read_text()), json.loads(raw), args.evidence.name, hashlib.sha256(raw).hexdigest(), ROOT)
    args.contract.write_text(json.dumps(result, sort_keys=True, separators=(',', ':'))+'\n')
