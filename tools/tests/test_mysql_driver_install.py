"""Linux setup refuses unqualified native binaries and retains bounded failures."""
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from tools import cdeadmin_install_mysql_driver as installer
from tools.reference_engine_demos import bootstrap

pytestmark = pytest.mark.skipif(installer.platform.system() != 'Linux', reason='Linux setup; native Windows/macOS use native.py')


def native():
    return {'connector_version': '26.7.0', 'native_query_attributes_abi': 1,
            'native_client_version': '9.7.0', 'extension_sha256': 'owned-extension',
            'python_cache_tag': 'cpython-314'}


@pytest.mark.parametrize('changed', [None, {'native_query_attributes_abi': None},
    {'native_client_version': '9.6.0'}, {'connector_version': '26.6.0'}])
def test_probe_requires_actual_imported_native_abi_client_and_connector(monkeypatch, changed):
    result = subprocess.CompletedProcess([], 1, '', 'unavailable') if changed is None else subprocess.CompletedProcess([], 0, json.dumps(native() | changed), '')
    monkeypatch.setattr(installer.subprocess, 'run', Mock(return_value=result))
    assert installer.probe() is None


def test_probe_target_precedes_other_python_paths(monkeypatch, tmp_path):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(native()), ''))
    monkeypatch.setattr(installer.subprocess, 'run', run)
    monkeypatch.setenv('PYTHONPATH', 'other-driver')
    assert installer.probe(tmp_path) == native()
    assert run.call_args.kwargs['env']['PYTHONPATH'].startswith(str(tmp_path) + installer.os.pathsep)


def test_matching_installed_extension_and_source_receipt_reuses_without_download(monkeypatch, tmp_path):
    receipt = tmp_path / 'current.json'
    record = {'source_sha256': installer.SOURCE_SHA256, 'patch_sha256': installer.sha(installer.ROOT / 'tools/driver_patches/mysql-connector-python-26.7.0-query-attributes.patch'), 'installed': native()}
    receipt.write_text(json.dumps(record))
    monkeypatch.setattr(installer, 'probe', Mock(return_value=native()))
    acquire = Mock(side_effect=AssertionError('A current qualified installation must not fetch SDKs'))
    monkeypatch.setattr(installer, 'acquire_sdk', acquire)
    assert installer.install(receipt, target=tmp_path / 'target') == record
    acquire.assert_not_called()


def test_bad_offline_source_stops_before_sdk_acquisition_or_install(monkeypatch, tmp_path):
    source = tmp_path / 'wrong.tar.gz'; source.write_bytes(b'wrong archive')
    acquire = Mock(); run = Mock()
    monkeypatch.setattr(installer, 'acquire_sdk', acquire)
    monkeypatch.setattr(installer.subprocess, 'run', run)
    with pytest.raises(ValueError, match='hash differs'):
        installer.install(tmp_path / 'current.json', archive=source, target=tmp_path / 'target')
    acquire.assert_not_called(); run.assert_not_called()


def test_corrupt_sdk_download_is_not_extracted(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.platform, 'libc_ver', lambda: ('glibc', '2.39'))
    monkeypatch.setattr(installer.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(installer.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(installer.shutil, 'which', lambda _: '/owned/dpkg-deb')
    monkeypatch.setattr(installer, 'download', Mock(side_effect=ValueError('SDK hash differs')))
    run = Mock(); monkeypatch.setattr(installer.subprocess, 'run', run)
    with pytest.raises(ValueError, match='SDK hash differs'): installer.acquire_sdk(tmp_path)
    run.assert_not_called()


@pytest.mark.parametrize('old', [None, 'changed-extension'])
def test_missing_or_changed_installation_rebuilds_and_preserves_bounded_compile_failure(monkeypatch, tmp_path, old):
    receipt = tmp_path / 'current.json'
    record = {'source_sha256': installer.SOURCE_SHA256, 'patch_sha256': installer.sha(installer.ROOT / 'tools/driver_patches/mysql-connector-python-26.7.0-query-attributes.patch'), 'installed': native()}
    if old:
        record['installed']['extension_sha256'] = old; receipt.write_text(json.dumps(record))
    monkeypatch.setattr(installer, 'probe', lambda _: native() if old else None)
    monkeypatch.setattr(installer, 'acquire_sdk', lambda directory: (directory, []))
    monkeypatch.setattr(installer, 'download', lambda url, checksum, path: path.write_bytes(b'owned source'))
    directories = []
    def failed(command, **kwargs):
        output = Path(command[command.index('--output') + 1]); output.mkdir(); directories.append(output.parent)
        (output / 'build.log').write_bytes(b'x' * (130 * 1024) + b'actual compiler failure')
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(installer.subprocess, 'run', failed)
    with pytest.raises(subprocess.CalledProcessError): installer.install(receipt, target=tmp_path / 'target')
    log = receipt.with_suffix('.failure.log').read_bytes()
    assert len(log) == 128 * 1024 and log.endswith(b'actual compiler failure')
    assert not any(path.exists() for path in directories)
    if old: assert json.loads(receipt.read_text()) == record
    else: assert not receipt.exists()


def test_demo_python_install_includes_native_correction_without_server_bootstrap(monkeypatch):
    run = Mock(); monkeypatch.setattr(bootstrap, 'run', run)
    bootstrap.install_python_requirements()
    assert run.call_count == 2
    assert run.call_args.args[0][1:4] == ['-B', '-m', 'tools.cdeadmin_install_mysql_driver']
    assert run.call_args.kwargs['cwd'] == bootstrap.REPOSITORY
    assert not any('docker' in str(value) for call in run.call_args_list for value in call.args)
