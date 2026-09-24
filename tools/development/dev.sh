#!/usr/bin/env bash
set -euo pipefail
umask 077
dev_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ -f "$dev_root/.venv/bin/activate" ]]; then
    source "$dev_root/.venv/bin/activate"
fi
source "$dev_root/tools/reference_engine_demos/environment.sh"
exec python3 "$dev_root/tools/development/manage.py" "$@"
