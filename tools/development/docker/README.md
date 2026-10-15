# Docker Compose development stack

Runs the CDEadmin web app in a container with **`web/pgadmin` bind-mounted** so Python
and React source edits on the host are picked up (Flask debug reloader for `.py` files).

## Quick start

From the repository root (Docker Desktop or Linux engine running):

```bash
docker compose -f docker-compose.dev.yml up --build
```

Open **http://127.0.0.1:5051** and sign in with:

| Field | Default |
| --- | --- |
| Email | `developer@example.com` |
| Password | `CDEadminDev-2026!` |

Override credentials via `.env.dev` (see `.env.dev.example`).

## What the image installs

- **`requirements.txt`** — application Python dependencies (always).
- **`tools/reference_engine_demos/requirements.txt`** — optional demo drivers; enable with
  `INSTALL_DEMO_REQUIREMENTS=1` at build time.
- **Frontend** — `yarn install --immutable` and `yarn webpacker` during image build.
  The image acquires the exact DDN source revision in the candidate manifest,
  verifies its source hashes, installs its pinned build dependencies, and runs
  the ordinary `tools/refresh_ddn.py` gate. Internet access is required.
  Unpublished DDN source changes must be reconciled before packaging.

Rebuild after changing `requirements.txt`, `web/package.json`, or `yarn.lock`:

```bash
docker compose -f docker-compose.dev.yml build web
```

### Build fails with `JavaScript heap out of memory`

This is usually **webpack**, not Corepack. `corepack enable` and `yarn install` finish first;
the failure happens on `yarn webpacker` when Node’s heap limit is too low for the bundle.

1. In **Docker Desktop → Settings → Resources**, give the VM at least **8 GiB RAM**
   (more if you raise `NODE_MAX_OLD_SPACE_SIZE`).
2. Increase the build heap, e.g. in `.env.dev`: `NODE_MAX_OLD_SPACE_SIZE=8192`, then rebuild.
3. Close other heavy containers during the frontend build step.

## Live code layout

| Host path | Container | Notes |
| --- | --- | --- |
| `./web/pgadmin` | `/cdeadmin/web/pgadmin` | Mounted; edit Python/JSX here |
| `./.devstate/application` | config SQLite, sessions, storage | Persists logins between restarts |

The image supplies compiled JavaScript and CSS through container-only temporary
mounts beneath the source mount. It copies only generated assets at startup;
JSX files are never copied back to the host. Python edits reload automatically.
After JSX, SCSS or other frontend changes, rebuild and recreate the web service:

```bash
docker compose -f docker-compose.dev.yml up --build --force-recreate web
```

## Databases

PostgreSQL is a separate container on the `cdeadmin-dev_default` network, so the
running web container can reach it as `postgresql:5432`. From the host it is
`127.0.0.1:55432`. MongoDB stays behind a Compose profile:

```bash
docker run -d --name cdeadmin-postgresql --network cdeadmin-dev_default \
  --network-alias postgresql -p 127.0.0.1:55432:5432 \
  -e POSTGRES_USER=cdeadmin_demo -e POSTGRES_PASSWORD=CDEadminDemo-2026! \
  -e POSTGRES_DB=cdeadmin_demo \
  -v cdeadmin-postgresql:/var/lib/postgresql/data postgres:16-alpine
docker compose -f docker-compose.dev.yml --profile mongodb up --build
```

| Service | Host connection | App hostname | Credentials |
| --- | --- | --- | --- |
| PostgreSQL | `127.0.0.1:55432` | `postgresql:5432` | user/db `cdeadmin_demo`, password `CDEadminDemo-2026!` |
| Firebird | `127.0.0.1:53050` | `firebird:3050`, file `/var/lib/firebird/data/cdeadmin_demo.fdb` | `SYSDBA` / `CDEadminDemo-2026!` |
| MySQL | `127.0.0.1:53306` | `mysql:3306` | user/db `cdeadmin_demo`, password `CDEadminDemo-2026!` |
| MariaDB | `127.0.0.1:53307` | `mariadb:3306` | user/db `cdeadmin_demo`, password `CDEadminDemo-2026!` |
| DuckDB | file `.devstate/application/cdeadmin_demo.duckdb` | `/cdeadmin/.devstate/application/cdeadmin_demo.duckdb` | no login |
| MongoDB | `127.0.0.1:27017` (or `MONGODB_PORT`) | `mongodb` | database `cdeadmin_demo`, no auth (local fixture) |

From **inside** the `web` container, use hostnames `postgresql` (port `5432`) and
`mongodb` instead of `127.0.0.1`.

Register the local PostgreSQL server in the running app:

```bash
docker compose -f docker-compose.dev.yml cp \
  tools/development/postgresql/register_local.py web:/tmp/register_postgresql.py
docker compose -f docker-compose.dev.yml exec web \
  /cdeadmin/.venv/bin/python /tmp/register_postgresql.py \
  --user developer@example.com
```

Register the local MongoDB profile (app running on the host or in `web`):

```bash
# Host venv / WSL after web is up:
python tools/development/mongodb/register_local.py --user developer@example.com
```

For MongoDB from the `web` container, point the profile host at `mongodb`.

## Configuration

On first start, `web/config_local.py` is created from
`tools/development/docker/config_local.docker.py` inside the container layer
(`DEBUG=True`, listen `0.0.0.0:5051`). To customize, copy that file to
`web/config_local.py` on the host and add a bind mount in `docker-compose.dev.yml`.

This stack is optional for **local UI and API development**. Windows and macOS
native development use [../NATIVE.md](../NATIVE.md)
and require no Docker or Linux runtime. The complete Linux demo estate uses
the `dev.sh` workflow documented in [../README.md](../README.md).
