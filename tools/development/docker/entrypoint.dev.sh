#!/usr/bin/env bash
set -euo pipefail

ROOT=/cdeadmin
WEB="${ROOT}/web"
VENV="${ROOT}/.venv/bin/python"
CONFIG="${WEB}/config_local.py"
TEMPLATE="${ROOT}/tools/development/docker/config_local.docker.py"

mkdir -p "${ROOT}/.devstate/application"

# Regenerate if missing or still using the old double-.. path (/.devstate/...).
if [[ ! -f "${CONFIG}" ]] \
    || grep -qF "'..', '..', '.devstate'" "${CONFIG}"; then
    cp "${TEMPLATE}" "${CONFIG}"
    chmod 600 "${CONFIG}"
fi

export PGADMIN_SETUP_EMAIL="${CDEADMIN_DEFAULT_EMAIL:-developer@example.com}"
export PGADMIN_SETUP_PASSWORD="${CDEADMIN_DEFAULT_PASSWORD:-CDEadminDev-2026!}"

if [[ ! -f "${ROOT}/.devstate/application/cdeadmin.db" ]]; then
    echo "Initializing CDEadmin configuration database..."
    "${VENV}" "${WEB}/setup.py" setup-db
fi

cd "${ROOT}"
export PYTHONUNBUFFERED=1
exec "${VENV}" "${WEB}/CDEadmin.py"
