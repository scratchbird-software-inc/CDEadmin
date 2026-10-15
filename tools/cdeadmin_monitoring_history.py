#!/usr/bin/env python3
"""Explicit ScratchBird archive administration; no monitored-engine connection."""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('initialize', 'maintain'))
    parser.add_argument('--config', type=Path, required=True,
                        help='Server-side JSON history configuration; password_env names an environment secret')
    args = parser.parse_args()
    # Import pgadmin through the same bootstrap used by standalone provider tools.
    from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
    from pgadmin.cdeadmin.workspace.monitoring_history import configured_history
    settings = json.loads(args.config.read_text())
    archive = configured_history(SimpleNamespace(config={'CDEADMIN_MONITORING_HISTORY': settings}))
    if archive is None:
        parser.error('History configuration must be enabled')
    try:
        getattr(archive, args.operation)()
    except Exception:
        print('History operation unconfirmed; inspect the destination before retrying.', file=sys.stderr)
        return 1
    print('History ' + args.operation + ' confirmed')
    return 0


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
