#!/usr/bin/env bash
set -euo pipefail

ROOT=/cdeadmin
WEB="${ROOT}/web"
VENV="${ROOT}/.venv/bin/python"
CONFIG="${WEB}/config_local.py"
TEMPLATE="${ROOT}/tools/development/docker/config_local.docker.py"

mkdir -p "${ROOT}/.devstate/application"

# Compose overlays these generated asset directories so the source bind mount
# cannot hide the bundle built into this image. Never copy over JSX sources.
cp -a "${ROOT}/frontend-generated/." "${WEB}/pgadmin/static/js/generated/"
cp -a "${ROOT}/frontend-css/." "${WEB}/pgadmin/static/css/"

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
