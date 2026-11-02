#!/usr/bin/env bash
set -euo pipefail
umask 077
dev_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ -f "$dev_root/.venv/bin/activate" ]]; then
    source "$dev_root/.venv/bin/activate"
fi
# Setup stages build and populate the interpreter, so they must not load the
# engine runtime's private libraries from LD_LIBRARY_PATH.
case "${1:-}" in
    interpreter|python) ;;
    *) source "$dev_root/tools/reference_engine_demos/environment.sh" ;;
esac
exec "${SCRATCHROBIN_PYTHON:-python3}" "$dev_root/tools/development/manage.py" "$@"
