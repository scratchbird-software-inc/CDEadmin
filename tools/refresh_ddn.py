#!/usr/bin/env python3
"""Capture ScratchWeaver's current standalone open DDN without editing it."""
import argparse
import json
import os
from pathlib import Path

from ddn_intake import CONTRACT, refresh as capture, verify_artifacts

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(os.environ.get('SCRATCHROBIN_DDN_SOURCE', str(ROOT.parent / 'ScratchWeaver')))
DEFAULT_WORK = Path(os.environ.get('SCRATCHROBIN_DDN_WORK',
                                  str(ROOT.parent / 'ChatGPT_Codex_1_Workarea/ddn-intake')))
DEST = ROOT / 'web/pgadmin/static/vendor/ddn/current'


def verify_vendored_only():
    manifest = json.loads((DEST / 'resource-manifest.json').read_text())
    verify_artifacts(DEST, manifest)
    print('DDN standalone artifacts verified (inspection only):', CONTRACT)


def refresh(source, work):
    return capture(source, work, DEST, Path(__file__))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    parser.add_argument('--verify-vendored', action='store_true')
    args = parser.parse_args()
    if args.verify_vendored:
        verify_vendored_only()
    else:
        refresh(args.source.resolve(), args.work.resolve())
