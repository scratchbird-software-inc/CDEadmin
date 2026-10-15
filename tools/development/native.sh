#!/usr/bin/env bash
set -euo pipefail
native_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$native_root"
exec "${SCRATCHROBIN_PYTHON:-python3}" tools/development/native.py "$@"
