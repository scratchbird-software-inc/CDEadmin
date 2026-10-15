#!/usr/bin/env python3
"""Acquire the exact clean DDN source recorded by this build candidate.

The ordinary refresh gate still verifies/rebuilds runtime and editor together.
Unpublished sister-project edits require a local source intake before packaging.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from refresh_ddn import inventory


def prepare(destination):
    manifest = json.loads((ROOT / 'web/pgadmin/static/vendor/ddn/current/'
                           'resource-manifest.json').read_text())
    expected = manifest['source']
    if expected['status']:
        raise RuntimeError('DDN has unpublished source changes. Package a '
                           'reviewed clean sister-project revision first.')
    subprocess.run([
        'git', '-c', 'core.autocrlf=false', 'clone',
        'https://github.com/scratchbird-software-inc/Diagram-Design-Notation.git',
        str(destination)], check=True)
    subprocess.run(['git', '-C', str(destination), 'checkout', '--detach',
                    expected['revision']], check=True)
    observed = inventory(destination)
    if observed != expected:
        raise RuntimeError('Acquired DDN source differs from candidate provenance')
    print('DDN source:', observed['revision'], 'status:', repr(observed['status']))
    for name in ('website/docs/developers/tool.md', 'notation/dist/ddn.d.ts'):
        print(name, '\n'.join((destination / name).read_text().splitlines()[:5]))
    subprocess.run(['npm', 'ci', '--ignore-scripts'], cwd=destination, check=True)


if __name__ == '__main__':
    prepare(Path(sys.argv[1]).resolve())
