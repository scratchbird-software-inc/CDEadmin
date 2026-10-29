"""Provision standalone DDN's exact native build tools in consumer-owned work.

No command runs in the sister checkout. Downloads are exact-version npm
artifacts with checked SHA-512, and the intake records the resulting binaries.
"""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import tarfile
from urllib.parse import quote, urlparse
from urllib.request import urlopen


def _verified(data, integrity):
    return integrity == 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()


def _package(name, version, destination, cache, expected=None):
    receipt = destination / '.ddn-tool.json'
    if receipt.is_file():
        saved = json.loads(receipt.read_text())
        if saved.get('package') == name and saved.get('version') == version and (not expected or saved.get('integrity') == expected):
            return saved
    with urlopen('https://registry.npmjs.org/' + quote(name, safe='') + '/' + quote(version, safe=''), timeout=30) as response:
        metadata = json.load(response)
    dist = metadata['dist']
    integrity = expected or dist.get('integrity')
    url = urlparse(dist['tarball'])
    if (metadata.get('version') != version or not isinstance(integrity, str) or
            not integrity.startswith('sha512-') or url.scheme != 'https' or url.hostname != 'registry.npmjs.org'):
        raise RuntimeError('Untrusted DDN build tool metadata')
    archive = cache / (name + '-' + version + '.tgz')
    cache.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        with urlopen(dist['tarball'], timeout=60) as response:
            data = response.read(128 * 1024 * 1024 + 1)
        if len(data) > 128 * 1024 * 1024 or not _verified(data, integrity):
            raise RuntimeError('DDN tool archive integrity/size mismatch')
        archive.write_bytes(data)
    if not _verified(archive.read_bytes(), integrity):
        raise RuntimeError('Cached DDN tool archive integrity mismatch')
    stage = destination.with_name(destination.name + '.pending')
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        with tarfile.open(archive, 'r:gz') as captured:
            for member in captured:
                path = PurePosixPath(member.name)
                if (not path.parts or path.parts[0] != 'package' or '..' in path.parts or
                        '\\' in member.name or not (member.isfile() or member.isdir())):
                    raise RuntimeError('Unsafe DDN tool archive member')
                if len(path.parts) == 1:
                    continue
                member.name = PurePosixPath(*path.parts[1:]).as_posix()
                captured.extract(member, stage, filter='data')
        saved = {'package': name, 'version': version, 'integrity': integrity,
                 'tarball': dist['tarball']}
        (stage / receipt.name).write_text(json.dumps(saved) + '\n')
        if destination.exists():
            shutil.rmtree(destination)
        stage.rename(destination)
        return saved
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def resolve(source, work):
    lock = json.loads((source / 'docs/Weaver-Specifications/implementation/contracts/library-lock.json').read_text())
    types = next(item for item in lock['libraries'] if item['package'] == 'typescript')
    tree = source / '.work/tools/toolchain'
    local_node = tree / ('node/node.exe' if os.name == 'nt' else 'node/bin/node')
    node = Path(os.environ.get('SCRATCHROBIN_DDN_NODE', local_node))
    typescript = Path(os.environ.get('SCRATCHROBIN_DDN_TYPESCRIPT', tree / 'typescript'))
    receipts = []
    system = {'Windows': 'win', 'Darwin': 'darwin', 'Linux': 'linux'}.get(platform.system())
    arch = {'AMD64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    if not system or not arch:
        raise RuntimeError('DDN requires a reviewed native Node platform or explicit tool overrides')
    tools, cache = work / 'toolchain', work / 'tool-cache'
    if not node.is_file():
        if 'SCRATCHROBIN_DDN_NODE' in os.environ:
            raise RuntimeError('Explicit DDN Node executable is missing')
        location = tools / 'node'
        receipts.append(_package(f'node-{system}-{arch}', lock['node'], location, cache))
        choices = [location / 'bin' / ('node.exe' if os.name == 'nt' else 'node'), location / 'node.exe']
        node = next((path for path in choices if path.is_file()), choices[0])
    if not (typescript / 'lib/typescript.js').is_file():
        if 'SCRATCHROBIN_DDN_TYPESCRIPT' in os.environ:
            raise RuntimeError('Explicit DDN TypeScript distribution is missing')
        typescript = tools / 'typescript'
        receipts.append(_package('typescript', types['version'], typescript, cache, types['integrity']))
    version = subprocess.check_output([str(node), '--version'], text=True).strip()
    if version != 'v' + lock['node'] or json.loads((typescript / 'package.json').read_text())['version'] != types['version']:
        raise RuntimeError('DDN tool versions differ from the adopted source lock')
    return node, typescript, receipts
