"""Content-bound native platform receipts; never infer full product release approval."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ('linux-x64', 'windows-x64', 'macos-x64', 'macos-arm64')
WORKFLOWS = ('editor', 'row_sql', 'templates', 'profiler', 'data_export',
             'test_data', 'metadata_search', 'blob_editor', 'ddn_sql', 'events',
             'recreate', 'registration')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def host_id(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    architecture = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine)
    host = {'Linux': 'linux', 'Windows': 'windows', 'Darwin': 'macos'}.get(system)
    if not architecture or not host or f'{host}-{architecture}' not in HOSTS:
        raise ValueError('Host is outside the declared Firebird qualification matrix')
    return f'{host}-{architecture}'


def source_snapshot(root=ROOT):
    """Bind all versioned/unignored source, preserving actual dirty-tree authority."""
    root = Path(root)
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others',
                                     '--exclude-standard'], cwd=root).split(b'\0')
    files = {}
    for raw in sorted(set(names)):
        if not raw:
            continue
        name = raw.decode('utf-8')
        selected = root / name
        if not selected.exists():
            continue
        if selected.is_symlink():
            import os
            data = os.readlink(selected).encode()
        else:
            data = selected.read_bytes()
            if name == 'web/pgadmin/static/vendor/ddn/current/resource-manifest.json':
                data = json.dumps(json.loads(data), sort_keys=True, separators=(',', ':')).encode()
        files[name] = hashlib.sha256(data).hexdigest()
    manifest = json.loads((root / 'web/pgadmin/static/vendor/ddn/current/resource-manifest.json').read_text(encoding='utf-8'))
    return {'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'status': subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True),
            'sha256': digest(files), 'files': files,
            'ddn_revision': manifest['source']['revision'],
            'ddn_artifacts': manifest['artifacts']}


def binary_identity(filename):
    path = Path(filename)
    with path.open('rb') as source:
        magic = source.read(4)
    kind = ('ELF' if magic == b'\x7fELF' else 'PE' if magic[:2] == b'MZ' else
            'Mach-O' if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe',
                                 b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf') else 'unknown')
    expected = {'Linux': 'ELF', 'Windows': 'PE', 'Darwin': 'Mach-O'}.get(platform.system())
    if kind != expected:
        raise ValueError('Client binary format does not match the native host')
    return {'name': path.name, 'format': kind, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def artifacts(root):
    """Only publish receipt/log evidence; runtime security databases stay private."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()
            and p.suffix in {'.json', '.xml', '.log', '.png'}
            and p.name not in {'platform.json', 'release.json'}
            and not any(part.startswith('owned-') for part in p.relative_to(root).parts)}


def inspect_receipt(path, expected_source):
    """Refuse missing, tampered, stale or partial native evidence independently."""
    path = Path(path)
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Platform receipt must be an object')
    errors = []
    if value.get('schema') != 'cdeadmin.firebird-platform-release.v1':
        errors.append('unsupported platform receipt schema')
    if value.get('host') not in HOSTS:
        errors.append('host outside required matrix')
    source = value.get('source', {})
    if (source.get('sha256') != expected_source or
            source.get('sha256') != digest(source.get('files', {}))):
        errors.append('source snapshot does not match the release candidate')
    if value.get('source_unchanged') is not True:
        errors.append('source changed during qualification')
    if value.get('complete') is not True or value.get('owned_state_removed') is not True:
        errors.append('platform qualification or owned cleanup incomplete')
    if value.get('failures') != []:
        errors.append('platform reports qualification failures')
    if value.get('runtime_template_unchanged') is not True:
        errors.append('runtime security template changed')
    if not str(value.get('python', '')).startswith('3.14.'):
        errors.append('Python 3.14 native proof missing')
    def read_artifact(relative):
        if not isinstance(relative, str) or relative not in value.get('artifacts', {}):
            raise ValueError('Required native artifact is not bound in the receipt')
        selected = path.parent / relative
        if not selected.resolve().is_relative_to(path.parent.resolve()):
            raise ValueError('Native artifact escapes its evidence root')
        return json.loads(selected.read_text(encoding='utf-8'))
    modes = {item.get('mode'): item for item in value.get('modes', [])}
    required = ('network', 'embedded', 'xnet', 'win-sspi') if value.get('host') == 'windows-x64' else ('network', 'embedded')
    if len(modes) != len(value.get('modes', [])) or set(modes) != set(required):
        errors.append('native mode inventory differs from the required matrix')
    for mode in required:
        proof = modes.get(mode, {})
        if proof.get('complete') is not True:
            errors.append(f'{mode}: missing successful native mode')
        checks = proof.get('checks', [])
        wanted = {'driver', 'workflows'} if mode in {'network', 'embedded'} else {'driver'}
        if ({item.get('check') for item in checks} != wanted or len(checks) != len(wanted) or
                any(item.get('status') != 'passed' for item in checks)):
            errors.append(f'{mode}: native runner checks incomplete')
        if mode in {'network', 'embedded'} and set(proof.get('workflows', [])) != set(WORKFLOWS):
            errors.append(f'{mode}: incomplete workflow inventory')
        if mode in {'network', 'embedded'} and proof.get('exhaustive_codecs') is not True:
            errors.append(f'{mode}: exhaustive codec proof missing')
        expected_format = 'PE' if value.get('host') == 'windows-x64' else 'Mach-O' if str(value.get('host')).startswith('macos-') else 'ELF'
        if proof.get('client_binary', {}).get('format') != expected_format:
            errors.append(f'{mode}: wrong native client binary format')
        try:
            native = read_artifact(proof.get('driver_receipt'))
            if (native.get('schema') != 'cdeadmin.firebird-driver-platform-proof.v1' or
                    native.get('complete') is not True or native.get('engine_version') != '5.0.4' or
                    native.get('driver_version') != '1.10.11' or
                    not str(native.get('python', '')).startswith('3.14.') or
                    any(native.get(key) is not True for key in
                        ('fixture_created', 'fixture_removed', 'handles_released')) or
                    native.get('failures') != []):
                errors.append(f'{mode}: native driver receipt is incomplete')
            provider_files = {name for name in source.get('files', {}) if
                name.startswith('web/pgadmin/cdeadmin/providers/firebird/') and
                len(Path(name).parts) == 6 and Path(name).suffix in {'.py', '.json'}}
            if set(native.get('source_sha256', {})) != provider_files:
                errors.append(f'{mode}: native provider source inventory incomplete')
            if native.get('client_library_sha256') != proof.get('client_binary', {}).get('sha256'):
                errors.append(f'{mode}: selected native library hash differs')
            required_checks = {'provider_create_and_independent_open',
                'metadata_scalar_array_blob_pending_visibility', 'rollback_and_committed_visibility',
                'bounded_blob_stream'}
            if mode != 'embedded':
                required_checks.add('native_services_attachment')
            if not required_checks <= set(native.get('checks', [])):
                errors.append(f'{mode}: native driver behavior inventory incomplete')
            if native.get('attachment_mode') != ('embedded' if mode == 'embedded' else 'network'):
                errors.append(f'{mode}: native attachment mode differs')
            for name, checksum in native.get('source_sha256', {}).items():
                if source.get('files', {}).get(name) != checksum:
                    errors.append(f'{mode}: stale native provider source binding')
            if not native.get('source_sha256') or native.get('runner_sha256') != source.get('files', {}).get(
                    'tools/cdeadmin_firebird_driver_platform_gate.py'):
                errors.append(f'{mode}: missing current driver runner binding')
            if 'remote_protocol' not in native or (mode == 'embedded' and native['remote_protocol'] is not None) or (mode != 'embedded' and not native.get('remote_protocol')):
                errors.append(f'{mode}: native transport was not observed')
            if mode == 'xnet' and native.get('remote_protocol') != 'XNET':
                errors.append('xnet: native shared-memory transport missing')
            if mode == 'win-sspi' and native.get('auth_method') != 'Win_Sspi':
                errors.append('win-sspi: native trusted authentication missing')
            if mode in {'network', 'embedded'}:
                if not {'legacy-codecs', 'gb18030-codec', 'unicode-fss-codec'} <= set(native.get('checks', [])):
                    errors.append(f'{mode}: exhaustive native conversion checks missing')
                workflow = read_artifact(proof.get('workflow_receipt'))
                observed = workflow.get('checks', [])
                if (workflow.get('schema') != 'cdeadmin.firebird-workflow-platform-proof.v1' or
                        workflow.get('attachment_mode') != mode or
                        workflow.get('complete') is not True or workflow.get('source_unchanged') is not True or
                        workflow.get('source', {}).get('sha256') != expected_source or
                        digest(workflow.get('source', {}).get('files', {})) != expected_source or
                        {item.get('check') for item in observed} != set(WORKFLOWS) or
                        len(observed) != len(WORKFLOWS) or
                        any(item.get('status') != 'passed' or item.get('proof', {}).get('passed') is not True or item.get('owned_databases_removed') is not True or
                            item.get('handles_released') is not True for item in observed)):
                    errors.append(f'{mode}: native workflow receipt is incomplete')
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            errors.append(f'{mode}: required native proof artifact unavailable')
    for relative, expected in value.get('artifacts', {}).items():
        selected = path.parent / relative
        if (not isinstance(relative, str) or Path(relative).is_absolute() or
                '..' in Path(relative).parts or selected.is_symlink() or
                not selected.resolve().is_relative_to(path.parent.resolve()) or
                not selected.is_file() or hashlib.sha256(selected.read_bytes()).hexdigest() != expected):
            errors.append('artifact integrity failed: ' + str(relative))
    if not value.get('artifacts'):
        errors.append('receipt has no preserved native artifacts')
    return value, errors


def compose(paths, expected_source):
    receipts = {}
    failures = []
    for path in paths:
        try:
            value, errors = inspect_receipt(path, expected_source)
            host = value.get('host')
            if host in receipts:
                errors.append('duplicate platform evidence')
            receipts[host] = {'receipt': str(path), 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                              'revision': value.get('source', {}).get('revision'), 'errors': errors}
            failures.extend({'host': host, 'reason': error} for error in errors)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            failures.append({'receipt': str(path), 'reason': type(error).__name__})
    for host in HOSTS:
        if host not in receipts:
            failures.append({'host': host, 'reason': 'native platform evidence missing'})
    return {'schema': 'cdeadmin.firebird-release-evidence.v1',
            'source_sha256': expected_source, 'platforms': receipts, 'failures': failures,
            'complete': not failures, 'backend_platform_qualified': not failures,
            'product_release_approved': False,
            'separate_acceptance': ['human form validation', 'platform UX/accessibility QA',
                                    'signed installer and installed-application QA',
                                    'live ScratchBird monitoring-history acceptance'],
            'scope': 'native Firebird driver and portable workflow qualification; no inferred product signoff'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--receipt', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compose(args.receipt, args.source_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'complete': result['complete'], 'failures': result['failures']}, indent=2))
    raise SystemExit(0 if result['complete'] else 1)
