"""Release aggregation refuses incomplete, stale and internally inconsistent proof."""
import hashlib
import json
from pathlib import Path
import pytest
from tools.firebird_release_evidence import HOSTS, WORKFLOWS, compose, digest, inspect_receipt, host_id

PROVIDER = 'web/pgadmin/cdeadmin/providers/firebird/provider.py'
RUNNER = 'tools/cdeadmin_firebird_driver_platform_gate.py'
SOURCE = {PROVIDER: 'a'*64, RUNNER: 'b'*64}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def platform_proof(root, host):
    value = {'schema': 'cdeadmin.firebird-platform-release.v1', 'host': host,
             'python': '3.14.8', 'complete': True, 'owned_state_removed': True,
             'runtime_template_unchanged': True, 'source_unchanged': True,
             'source': {'files': SOURCE, 'sha256': digest(SOURCE), 'revision': 'c'*40},
             'modes': [], 'artifacts': {}, 'failures': []}
    for mode in (('network', 'embedded', 'xnet', 'win-sspi') if host == 'windows-x64' else ('network', 'embedded')):
        native = {'schema': 'cdeadmin.firebird-driver-platform-proof.v1',
                  'complete': True, 'engine_version': '5.0.4', 'driver_version': '1.10.11',
                  'python': '3.14.8', 'fixture_created': True, 'fixture_removed': True,
                  'handles_released': True, 'failures': [], 'source_sha256': {PROVIDER: SOURCE[PROVIDER]},
                  'runner_sha256': SOURCE[RUNNER], 'client_library_sha256': 'd'*64,
                  'attachment_mode': 'embedded' if mode == 'embedded' else 'network',
                  'checks': ['legacy-codecs', 'gb18030-codec', 'unicode-fss-codec',
                    'provider_create_and_independent_open', 'metadata_scalar_array_blob_pending_visibility',
                    'rollback_and_committed_visibility', 'bounded_blob_stream',
                    'native_gb18030_profile_roundtrip', 'native_services_attachment'],
                  'remote_protocol': None if mode == 'embedded' else 'XNET' if mode == 'xnet' else 'TCPv4',
                  'authenticated_user': 'SYSDBA' if mode == 'win-sspi' else None,
                  'auth_method': 'Win_Sspi' if mode == 'win-sspi' else 'Srp'}
        driver_path = mode + '/driver/summary.json'
        workflow_path = mode + '/workflows/summary.json'
        workflow = {'schema': 'cdeadmin.firebird-workflow-platform-proof.v1',
                    'attachment_mode': mode, 'complete': True, 'source_unchanged': True, 'source': value['source'],
                    'checks': [{'check': name, 'status': 'passed', 'proof': {'passed': True},
                                'handles_released': True, 'owned_databases_removed': True} for name in WORKFLOWS]}
        proof = {'mode': mode, 'complete': True, 'exhaustive_codecs': True,
                 'checks': [{'check': name, 'status': 'passed'} for name in
                            (('driver', 'workflows') if mode in {'network', 'embedded'} else ('driver',))],
                 'workflows': list(WORKFLOWS), 'driver_receipt': driver_path,
                 'workflow_receipt': workflow_path,
                 'client_binary': {'format': 'PE' if host == 'windows-x64' else 'ELF' if host == 'linux-x64' else 'Mach-O', 'sha256': 'd'*64}}
        value['modes'].append(proof)
        value['artifacts'][driver_path] = write(root/driver_path, native)
        value['artifacts'][workflow_path] = write(root/workflow_path, workflow)
    write(root/'platform.json', value)
    return root/'platform.json'


def mutate(path, action, nested=None):
    value = json.loads(path.read_text())
    if nested:
        target = path.parent/nested
        data = json.loads(target.read_text());action(data)
        value['artifacts'][nested] = write(target, data)
    else:
        action(value)
    write(path, value)


def test_complete_backend_matrix_never_approves_product_release(tmp_path):
    paths = [platform_proof(tmp_path/host, host) for host in HOSTS]
    result = compose(paths, digest(SOURCE))
    assert result['complete'] and result['backend_platform_qualified']
    assert not result['product_release_approved']
    assert 'human form validation' in result['separate_acceptance']


def test_missing_platform_and_duplicate_evidence_are_not_success(tmp_path):
    path = platform_proof(tmp_path/'linux', 'linux-x64')
    result = compose([path, path], digest(SOURCE))
    assert not result['complete']
    assert any(v['reason'] == 'duplicate platform evidence' for v in result['failures'])
    assert sum(v['reason'] == 'native platform evidence missing' for v in result['failures']) == 3


@pytest.mark.parametrize('action', [
    lambda x:x.update(complete=False), lambda x:x.update(source_unchanged=False),
    lambda x:x.update(owned_state_removed=False), lambda x:x.update(runtime_template_unchanged=False),
    lambda x:x.update(python='3.12.9'), lambda x:x['source'].update(sha256='0'*64),
    lambda x:x['modes'].pop(), lambda x:x['modes'][0].update(workflows=['editor']),
    lambda x:x['modes'][0].update(exhaustive_codecs=False),
    lambda x:x['modes'][0]['client_binary'].update(format='ELF'),
    lambda x:x.update(failures=[{'scope': 'server'}]),
    lambda x:x['modes'].append(x['modes'][0]),
    lambda x:x['modes'][0]['checks'][0].update(status='failed'),
])
def test_top_level_false_success_is_refused(tmp_path, action):
    path = platform_proof(tmp_path/'win', 'windows-x64');mutate(path, action)
    assert inspect_receipt(path, digest(SOURCE))[1]


@pytest.mark.parametrize('action', [
    lambda x:x.update(complete=False), lambda x:x.update(engine_version='6.0.0'),
    lambda x:x.update(driver_version='2.0.0'), lambda x:x.update(handles_released=False),
    lambda x:x.update(fixture_removed=False), lambda x:x.update(failures=[{'stage':'native'}]),
    lambda x:x.update(client_library_sha256='0'*64), lambda x:x['source_sha256'].clear(),
    lambda x:x.update(runner_sha256='0'*64), lambda x:x.update(remote_protocol=None),
    lambda x:x.update(checks=[]),
])
def test_rehashed_but_failed_native_driver_cannot_be_hidden(tmp_path, action):
    path = platform_proof(tmp_path/'win', 'windows-x64')
    mutate(path, action, 'network/driver/summary.json')
    assert inspect_receipt(path, digest(SOURCE))[1]


@pytest.mark.parametrize('mode,field,value', [('xnet','remote_protocol','TCPv4'),
    ('win-sspi','auth_method','Srp'), ('win-sspi','authenticated_user','unexpected')])
def test_windows_specific_transports_need_actual_observations(tmp_path, mode, field, value):
    path = platform_proof(tmp_path/'win', 'windows-x64')
    mutate(path, lambda x:x.update({field:value}), mode+'/driver/summary.json')
    assert inspect_receipt(path, digest(SOURCE))[1]


def test_windows_mapped_trusted_auth_retains_native_plugin_evidence(tmp_path):
    path = platform_proof(tmp_path/'win', 'windows-x64')
    mutate(path, lambda x:x.update(auth_method='Mapped from Win_Sspi'), 'win-sspi/driver/summary.json')
    assert inspect_receipt(path, digest(SOURCE))[1] == []


@pytest.mark.parametrize('action', [
    lambda x:x.update(complete=False), lambda x:x.update(source_unchanged=False),
    lambda x:x['checks'].pop(), lambda x:x['checks'][0].update(status='skipped'),
    lambda x:x['checks'][0].update(handles_released=False),
    lambda x:x['checks'][0]['proof'].update(passed=False),
])
def test_rehashed_partial_workflows_are_not_qualified(tmp_path, action):
    path = platform_proof(tmp_path/'linux', 'linux-x64')
    mutate(path, action, 'embedded/workflows/summary.json')
    assert inspect_receipt(path, digest(SOURCE))[1]


def test_tampering_missing_artifact_and_escape_are_refused(tmp_path):
    path = platform_proof(tmp_path/'linux', 'linux-x64')
    artifact = path.parent/'network/driver/summary.json'
    artifact.write_text('{}')
    assert any('integrity' in reason for reason in inspect_receipt(path, digest(SOURCE))[1])
    artifact.unlink()
    assert inspect_receipt(path, digest(SOURCE))[1]
    mutate(path, lambda x:x['artifacts'].update({'../elsewhere.json':'a'*64}))
    assert inspect_receipt(path, digest(SOURCE))[1]


@pytest.mark.parametrize('system,machine,expected', [('Windows','AMD64','windows-x64'),
    ('Darwin','arm64','macos-arm64'), ('Darwin','x86_64','macos-x64'), ('Linux','x86_64','linux-x64')])
def test_host_identity_uses_native_architecture(system, machine, expected):
    assert host_id(system,machine) == expected


@pytest.mark.parametrize('value', [[], None, {'modes': [None]}, {'source': None}])
def test_malformed_receipts_fail_closed_without_aborting_inventory(tmp_path, value):
    malformed = tmp_path/'malformed.json'
    write(malformed, value)
    valid = platform_proof(tmp_path/'linux', 'linux-x64')
    result = compose([malformed, valid], digest(SOURCE))
    assert not result['complete']
    assert result['platforms']['linux-x64']['errors'] == []
    assert any(item.get('receipt') == str(malformed) for item in result['failures'])
