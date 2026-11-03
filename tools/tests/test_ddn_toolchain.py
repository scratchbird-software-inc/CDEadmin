"""Pinned tool acquisition refuses tampering and unsafe package members."""
import base64
import hashlib
import io
import json
import tarfile

import pytest

import ddn_toolchain as tools


def package_bytes(name='package/lib/typescript.js', link=None):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w:gz') as archive:
        member = tarfile.TarInfo(name)
        if link:
            member.type = tarfile.SYMTYPE
            member.linkname = link
            archive.addfile(member)
        else:
            member.size = 6
            archive.addfile(member, io.BytesIO(b'export'))
    return result.getvalue()


def registry(monkeypatch, archive, *, version='1.2.3', tarball='https://registry.npmjs.org/typescript/-/typescript.tgz'):
    integrity = 'sha512-' + base64.b64encode(hashlib.sha512(archive).digest()).decode()
    metadata = {'version': version, 'dist': {'integrity': integrity, 'tarball': tarball}}
    requests = []

    def open_url(url, **_kwargs):
        requests.append(url)
        return io.BytesIO(archive if url == tarball else json.dumps(metadata).encode())

    monkeypatch.setattr(tools, 'urlopen', open_url)
    return integrity, requests


def test_verified_install_and_offline_receipt(tmp_path, monkeypatch):
    archive = package_bytes()
    integrity, requests = registry(monkeypatch, archive)
    destination, cache = tmp_path / 'installed', tmp_path / 'cache'
    receipt = tools._package('typescript', '1.2.3', destination, cache, integrity)
    assert (destination / 'lib/typescript.js').read_bytes() == b'export'
    assert receipt['integrity'] == integrity and len(requests) == 2
    monkeypatch.setattr(tools, 'urlopen', lambda *_a, **_k: pytest.fail('offline receipt fetched the network'))
    assert tools._package('typescript', '1.2.3', destination, cache, integrity) == receipt


@pytest.mark.parametrize('name,link', [('package/../../escape', None), ('/outside', None), ('package/lib/link', '../../outside'), ('package\\escape', None)])
def test_unsafe_archive_preserves_installed_tools(tmp_path, monkeypatch, name, link):
    archive = package_bytes(name, link)
    registry(monkeypatch, archive)
    destination = tmp_path / 'installed'
    destination.mkdir()
    (destination / 'existing').write_text('preserved')
    with pytest.raises(RuntimeError, match='Unsafe'):
        tools._package('typescript', '1.2.3', destination, tmp_path / 'cache')
    assert (destination / 'existing').read_text() == 'preserved'
    assert not (tmp_path / 'escape').exists()
    assert not (tmp_path / 'installed.pending').exists()


def test_tampered_cached_archive_is_rejected(tmp_path, monkeypatch):
    registry(monkeypatch, package_bytes())
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'typescript-1.2.3.tgz').write_bytes(b'tampered')
    with pytest.raises(RuntimeError, match='integrity mismatch'):
        tools._package('typescript', '1.2.3', tmp_path / 'installed', cache)
    assert not (tmp_path / 'installed').exists()


@pytest.mark.parametrize('version,tarball', [('9.9.9', 'https://registry.npmjs.org/archive.tgz'), ('1.2.3', 'http://registry.npmjs.org/archive.tgz'), ('1.2.3', 'https://other.example/archive.tgz')])
def test_registry_version_and_origin_are_pinned(tmp_path, monkeypatch, version, tarball):
    registry(monkeypatch, package_bytes(), version=version, tarball=tarball)
    with pytest.raises(RuntimeError, match='Untrusted'):
        tools._package('typescript', '1.2.3', tmp_path / 'installed', tmp_path / 'cache')


def test_explicit_native_versions_must_match_source_lock(tmp_path, monkeypatch):
    lock = tmp_path / tools.LIBRARY_LOCK
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({'node': '24.22.1', 'libraries': [{'package': 'typescript', 'version': '6.0.3', 'integrity': 'sha512-pinned'}]}))
    node, typescript = tmp_path / 'node', tmp_path / 'typescript'
    node.touch()
    (typescript / 'lib').mkdir(parents=True)
    (typescript / 'lib/typescript.js').touch()
    (typescript / 'package.json').write_text('{"version":"6.0.3"}')
    monkeypatch.setenv('SCRATCHROBIN_DDN_NODE', str(node))
    monkeypatch.setenv('SCRATCHROBIN_DDN_TYPESCRIPT', str(typescript))
    monkeypatch.setattr(tools.subprocess, 'check_output', lambda *_a, **_k: 'v22.0.0\n')
    with pytest.raises(RuntimeError, match='versions differ'):
        tools.resolve(tmp_path, tmp_path / 'work')


def test_optimizer_installs_only_locked_packages_for_this_platform(tmp_path, monkeypatch):
    lock = tmp_path / tools.OPTIMIZER_LOCK
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({'packages': {'': {'name': 'ddn-production-build-tools'},
        'node_modules/esbuild': {'version': '0.28.2', 'integrity': 'sha512-esbuild'},
        'node_modules/@esbuild/linux-x64': {'version': '0.28.2', 'integrity': 'sha512-linux', 'optional': True, 'os': ['linux'], 'cpu': ['x64']},
        'node_modules/@esbuild/win32-x64': {'version': '0.28.2', 'integrity': 'sha512-win', 'optional': True, 'os': ['win32'], 'cpu': ['x64']}}}))
    installed = []
    monkeypatch.setattr(tools, '_package', lambda name, version, destination, cache, expected=None:
                        installed.append((name, version, destination, expected)) or {'package': name})
    monkeypatch.setattr(tools.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(tools.platform, 'machine', lambda: 'x86_64')
    modules, receipts = tools.optimizer(tmp_path, tmp_path / 'work')
    assert [(name, expected) for name, _version, _destination, expected in installed] == [
        ('@esbuild/linux-x64', 'sha512-linux'), ('esbuild', 'sha512-esbuild')]
    assert all(destination == modules / name for name, _version, destination, _expected in installed)
    for bad in ({'node_modules/a/node_modules/b': {'version': '1', 'integrity': 'sha512-x'}},
                {'node_modules/unpinned': {'version': '1'}}):
        lock.write_text(json.dumps({'packages': bad}))
        with pytest.raises(RuntimeError, match='requires review'):
            tools.optimizer(tmp_path, tmp_path / 'work')
