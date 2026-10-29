#!/usr/bin/env python3
"""Acquire the exact clean DDN source recorded by this build candidate.

The ordinary refresh gate still verifies/rebuilds runtime and editor together.
Unpublished sister-project edits require a local source intake before packaging.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from ddn_intake import inventory


def prepare(destination):
    manifest = json.loads((ROOT / 'web/pgadmin/static/vendor/ddn/current/'
                           'resource-manifest.json').read_text())
    expected = manifest['source']
    if expected['status']:
        raise RuntimeError('DDN has unpublished source changes. Package a '
                           'reviewed clean sister-project revision first.')
    source_url = os.environ.get('CDEADMIN_DDN_SOURCE_URL')
    if not source_url:
        raise RuntimeError('Set CDEADMIN_DDN_SOURCE_URL to an authorized reviewed ddn-next-1 source; the obsolete public DDN repository is not a fallback.')
    subprocess.run([
        'git', '-c', 'core.autocrlf=false', 'clone',
        source_url,
        str(destination)], check=True)
    subprocess.run(['git', '-C', str(destination), 'checkout', '--detach',
                    expected['revision']], check=True)
    observed = inventory(destination)
    if observed != expected:
        raise RuntimeError('Acquired DDN source differs from candidate provenance')
    print('DDN source:', observed['revision'], 'status:', repr(observed['status']))
    for name in ('project/ddn/README.md', 'project/ddn/packages/types/src/browser.d.ts'):
        print(name, '\n'.join((destination / name).read_text().splitlines()[:5]))
    # Refresh provisions exact native tools in the consumer work area.
    # No bootstrap writes into the source checkout.


if __name__ == '__main__':
    prepare(Path(sys.argv[1]).resolve())
