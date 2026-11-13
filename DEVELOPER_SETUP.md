# ScratchRobin (CDEadmin) Developer Onboarding, Docker Estate & Test Database Guide

This document provides complete, step-by-step instructions for a new developer cloning the repository for the first time:

1. **Cloning the repository and mandatory sister repository (`Diagram-Design-Notation`)**
2. **Installing exact host prerequisites, Python 3.14, Node 22, Go 1.25.5+, JDK 17+, and Docker Engine**
3. **Building the backend, DDN-refreshed frontend bundle, native client tools, and Electron desktop runtime**
4. **Downloading and managing all 29 pinned Docker images used across the 26 reference-engine profiles**
5. **Creating, seeding, verifying, and registering test databases** — both the canonical `cdeadmin_demo` estate, isolated developer test databases (`dev.sh create-db`), and adding new engine test fixtures

> **Platform note:** Primary full-estate development runs on **x86_64 Linux** (Ubuntu 24.04 LTS native, WSL2 Ubuntu 24.04 with local Docker Engine, or an x86_64 Linux VM). For host-native Windows x64 and macOS development without Docker/Linux `.so` clients, also see [tools/development/NATIVE.md](tools/development/NATIVE.md).

---

## 1. Repository Layout & Cloning

ScratchRobin's frontend and schema/diagram tools consume the standalone open **Diagram-Design-Notation (`ddn-next-1`)** library before every build and commit-validating test run. Clone **both** repositories side by side in a local Linux filesystem directory (on WSL2, always use `/home/<user>/...`, never `/mnt/c/...`):

```bash
mkdir -p ~/src
cd ~/src

# 1. Clone ScratchRobin (CDEadmin) on the shared development branch (master)
git clone https://github.com/scratchbird-software-inc/CDEadmin.git

# 2. Clone the mandatory public Diagram-Design-Notation sister repository next to it
git clone https://github.com/scratchbird-software-inc/Diagram-Design-Notation.git

cd ~/src/CDEadmin
```

By default, `tools/refresh_ddn.py` reads `../Diagram-Design-Notation` (`subtree project/ddn`). If you place that checkout elsewhere or want an explicit disposable build directory for DDN capture, export:

```bash
export SCRATCHROBIN_DDN_SOURCE="$HOME/src/Diagram-Design-Notation"
export SCRATCHROBIN_DDN_WORK="/tmp/sr-ddn-intake"
```

---

## 2. Host Prerequisites & Toolchain Installation (Ubuntu 24.04 x86_64)

### 2.1 System Build & Native Driver Libraries

```bash
sudo apt update
sudo apt install -y \
  git ca-certificates curl build-essential pkg-config cmake \
  python3 python3-venv python3-dev \
  libpq-dev libkrb5-dev libmariadb-dev libmariadb-dev-compat \
  libssl-dev libffi-dev libsnappy-dev zlib1g-dev libreadline-dev \
  tcl-dev default-jdk libtommath1 libncurses6
```

### 2.2 Required Tool Versions

| Tool | Required Version | Purpose |
| --- | --- | --- |
| **Docker Engine + Compose v2** | Current Linux `amd64` daemon (`unix:///var/run/docker.sock`) | Runs the 22 Docker-backed reference database engines and extracts exact native clients |
| **Python** | **CPython 3.14+** (standard GIL build; `python3.14t` is qualification-only) | Runs `CDEadmin.py` backend, provider adapters, and verification gates |
| **Node.js + Corepack** | **Node.js 22 LTS** (tested `22.22.x`) with `corepack enable` | Installs immutable Yarn lockfile packages and builds Webpack/React bundles + Electron runtime |
| **Go** | **Go 1.25.5 or newer** | Compiles the repository's native `cdeadmin-tikv-helper` binary |
| **Java JDK** | **JDK 17+** (`javac`, `jar`) | Compiles Cassandra 5.0.8 trigger/JMX auth JARs and Apache Ignite 2.17.0 fixture JARs |

1. **Enable Corepack** so Yarn uses the exact version pinned in `web/package.json`:
   ```bash
   corepack enable
   ```
2. **Select or Build CPython 3.14**:
   - **Fast setup (via `uv` or system Python 3.14):**
     ```bash
     uv python install 3.14
     export SCRATCHROBIN_PYTHON="$(uv python find 3.14)"
     ```
   - **Full SQLite 3.53.0 dynamic-link reference interpreter (optional, required only for the multi-version SQLite C-helper qualification matrix):**
     ```bash
     bash tools/development/dev.sh interpreter
     export SCRATCHROBIN_PYTHON="$PWD/.native/python/bin/python3.14"
     ```
3. **OpenSearch Kernel Parameter (recommended if testing OpenSearch):**
   ```bash
   sysctl vm.max_map_count
   # If below 262144:
   sudo sysctl -w vm.max_map_count=262144
   ```
4. **Run the Non-Destructive Preflight Doctor:**
   ```bash
   bash tools/development/dev.sh doctor
   ```
   Confirm every required line prints `OK:` (including `DDN sister checkout`).

---

## 3. Building the Project (Backend, Frontend, Native Clients & Desktop App)

Run the three build stages in order from the repository root:

```bash
# Stage 1: Create .venv, install web + demo + regression Python packages,
#          compile patched MySQL 9.7.0 & MariaDB 12.2.2 C connectors, and run `pip check`
bash tools/development/dev.sh python

# Stage 2: Refresh standalone DDN (`tools/refresh_ddn.py`), run `corepack yarn install --immutable`,
#          and build the production React/Webpack assets (uses 8 GiB Node heap by default;
#          override with CDEADMIN_NODE_HEAP_MB=8192 if needed)
bash tools/development/dev.sh frontend

# Stage 3: Pre-pull client images (if not cached), compile SQLite 3.53.0 CLI + TiKV Go helper
#          + Ignite Java fixture, extract exact FoundationDB/Firebird/MariaDB/MySQL Shell/
#          Cassandra/YugabyteDB clients, and render runtime/connection_profiles.json
bash tools/development/dev.sh clients
```

> **Mandatory DDN Freshness Rule:** `dev.sh frontend` automatically refreshes DDN before building. Whenever you invoke `pytest`, `corepack yarn test`, or `webpack` directly instead of `dev.sh frontend`, run `bash tools/development/dev.sh ddn` first.

### 3.1 Configuring & Launching the Web Server Mode (`127.0.0.1:5051`)

`dev.sh run` requires `web/config_local.py` and an initialized SQLite configuration database (`.devstate/application/`):

```bash
# 1. Create web/config_local.py (never overwrites an existing config)
bash tools/development/dev.sh configure

# 2. Initialize the local CDEadmin config database (prompts for your local dev login email & password)
bash tools/development/dev.sh init

# 3. Start the web server on http://127.0.0.1:5051
bash tools/development/dev.sh run
```

### 3.2 Building & Launching the Electron Desktop Application (`runtime/`)

ScratchRobin's desktop shell lives in `runtime/` and automatically spawns `.venv/bin/python3 web/CDEadmin.py` internally:

```bash
cd runtime
corepack yarn install

# One-time Linux SUID sandbox setup (required by Chromium/Electron on Linux;
# never pass --no-sandbox):
sudo chown root:root node_modules/electron/dist/chrome-sandbox
sudo chmod 4755 node_modules/electron/dist/chrome-sandbox

# Launch the ScratchRobin desktop app with native database client libraries on PATH/LD_LIBRARY_PATH:
source ../tools/reference_engine_demos/environment.sh
corepack yarn start
```

---

## 4. Docker Images to Download and Use

All Docker fixtures are strictly version-pinned (never `:latest`), attach to the isolated bridge network `cdeadmin-demo-net`, bind ports to loopback (`127.0.0.1`, plus `127.0.0.2`/`127.0.0.3` for 3-node Cassandra, and host IP for 4-store TiKV peer advertise), and persist state in named `cdeadmin-demo-*` Docker volumes.

### 4.1 Automated Image Inspection & Pre-Pull Commands

Use `dev.sh images` to inspect which pinned images are already cached locally vs missing, and `dev.sh pull` to download them ahead of time:

```bash
# Check status (present vs missing) of all 29 pinned Docker images:
bash tools/development/dev.sh images

# Pull only the 7 images needed by `dev.sh clients` host-tool extraction:
bash tools/development/dev.sh pull bootstrap

# Pull the 14 single-container everyday relational & NoSQL servers (recommended first step):
bash tools/development/dev.sh pull core

# Pull images for one specific engine (e.g., postgresql, firebird, vitess, milvus, tidb):
bash tools/development/dev.sh pull postgresql

# Pull all 26 standard reference-estate images:
bash tools/development/dev.sh pull all

# Pull all 29 images including opt-in TiDB TiCDC, BR, and TiFlash components:
bash tools/development/dev.sh pull all --include-opt-in
```

### 4.2 Complete Pinned Docker Image Reference Table (All 29 Images)

> **Demo Password Note:** Where `<DEMO_PASSWORD>` is shown below, the fixed local-only demonstration credential is `CDEadminDemo-2026!`. Never expose demo ports to a LAN or reuse demo credentials outside local disposable containers.

| Engine / Component | Exact Docker Image to Download | Container Name(s) | Host Loopback Port(s) | Default Demo User / Auth & Target DB | Client Extraction (`dev.sh clients`) |
| --- | --- | --- | --- | --- | --- |
| **PostgreSQL 18.3** (`postgresql`) | `postgres:18.3` | `cdeadmin-demo-postgresql` | `127.0.0.1:55432` -> `5432` | `cdeadmin_demo` / `<DEMO_PASSWORD>`, DB `cdeadmin_demo` | Uses host `libpq` / `psycopg` |
| **Firebird 5.0.4** (`firebird`) | `firebirdsql/firebird:5.0.4` | `cdeadmin-demo-firebird` | `127.0.0.1:53050` -> `3050` | `SYSDBA` / `<DEMO_PASSWORD>`, `/var/lib/firebird/data/cdeadmin_demo.fdb` | Extracts `libfbclient.so.5.0.4` |
| **MySQL 9.7.0** (`mysql`) | `mysql:9.7.0` | `cdeadmin-demo-mysql` | `127.0.0.1:53306` -> `3306` | `cdeadmin_demo` (and `root`) / `<DEMO_PASSWORD>`, DB `cdeadmin_demo` | Extracts `mysqlsh` 9.7.0 + private OpenSSL 3.5.1 |
| **MariaDB 12.2.2** (`mariadb`) | `mariadb:12.2.2` | `cdeadmin-demo-mariadb` | `127.0.0.1:53307` -> `3306` | `cdeadmin_demo` (and `root`) / `<DEMO_PASSWORD>`, DB `cdeadmin_demo` (ROW binlog) | Extracts `mariadb`, `mariadb-dump`, `mariadb-upgrade`, `mariadb-binlog`, `mariadb-admin` |
| **Redis 8.6.2** (`redis`) | `redis:8.6.2` | `cdeadmin-demo-redis` | `127.0.0.1:56379` -> `6379` | No password (`default`), DB `0` (AOF enabled) | Python `redis` client |
| **MongoDB 8.2.6** (`mongodb`) | `mongo:8.2.6` | `cdeadmin-demo-mongodb` | `127.0.0.1:57017` -> `27017` | Unauthenticated local fixture, DB `cdeadmin_demo` | Python `pymongo` client |
| **ClickHouse 25.12** (`clickhouse`) | `clickhouse/clickhouse-server:25.12.10.7` | `cdeadmin-demo-clickhouse` | `127.0.0.1:58123` (HTTP), `59001` (native) | `cdeadmin_demo` / `<DEMO_PASSWORD>`, DB `cdeadmin_demo` | HTTP / native adapter |
| **CockroachDB 26.1.3** (`cockroachdb`) | `cockroachdb/cockroach:v26.1.3` | `cdeadmin-demo-cockroachdb` | `127.0.0.1:56257` (SQL), `58081` (HTTP) | `root` (insecure local mode), DB `cdeadmin_demo` | Generates `runtime/cockroach_tools/cockroach` wrapper |
| **Dolt 1.86.6** (`dolt`) | `dolthub/dolt-sql-server:1.86.6` | `cdeadmin-demo-dolt` | `127.0.0.1:53308` -> `3306` | `root` (passwordless local), DB `cdeadmin_demo` | MySQL protocol connector |
| **immudb 1.11.0** (`immudb`) | `codenotary/immudb:1.11.0` | `cdeadmin-demo-immudb` | `127.0.0.1:53322` (gRPC), `55435` (PG SQL), `58082` (Web), `59497` (metrics) | `immudb` / `immudb`, DB `cdeadmin_demo` | gRPC / PG wire adapter |
| **InfluxDB 3.9.0** (`influxdb`) | `influxdb:3.9.0-core` | `cdeadmin-demo-influxdb` | `127.0.0.1:58181` -> `8181` | `--without-auth` local mode, DB `cdeadmin_demo` | HTTP v3 API |
| **Neo4j 2026.04.0** (`neo4j`) | `neo4j:2026.04.0-enterprise` | `cdeadmin-demo-neo4j` | `127.0.0.1:57687` (Bolt), `57474` (HTTP) | `neo4j` / `<DEMO_PASSWORD>`, DB `neo4j` | Bolt driver + `/cdeadmin-tools` bind mount |
| **OpenSearch 3.6.0** (`opensearch`, `opensearch_sql_ppl`) | `opensearchproject/opensearch:3.6.0` | `cdeadmin-demo-opensearch` | `127.0.0.1:59200` (REST), `59600` | Security plugin disabled locally, index `cdeadmin-work-orders` | REST + SQL/PPL adapters |
| **XTDB 2.1.0** (`xtdb`) | `ghcr.io/xtdb/xtdb:2.1.0` | `cdeadmin-demo-xtdb` | `127.0.0.1:55434` (PG wire), `58083` (HTTP/healthz) | `xtdb`, DB `xtdb` | PG wire + HTTP adapter |
| **Apache Ignite 2.17.0** (`apache_ignite`) | `apacheignite/ignite:2.17.0` | `cdeadmin-demo-apache-ignite`, `...-2` (2 nodes) | `127.0.0.1:51080` (thin), `58080` (REST) | `ignite` / `ignite` | Extracts Ignite JARs & compiles `cdeadmin-ignite-fixture.jar` |
| **Apache Cassandra 5.0.8** (`cassandra`) | `cassandra:5.0.8` | `cdeadmin-demo-cassandra`, `...-2`, `...-3` (3-node quorum) | `127.0.0.1..3:19042` (CQL), `127.0.0.1..3:17199` (JMX) | `cassandra` / `<DEMO_PASSWORD>`, keyspace `cdeadmin_demo` | Extracts `cqlsh`, `nodetool`, `sstableloader` + builds trigger JAR |
| **FoundationDB 7.3.77** (`foundationdb`) | `foundationdb/foundationdb:7.3.77` | `cdeadmin-demo-foundationdb` (4 processes) | `127.0.0.1:54500..54503` | Cluster file `runtime/fdb.cluster` | Extracts `fdbcli`, `fdbbackup`, `fdbrestore`, `libfdb_c.so` |
| **YugabyteDB 2025.2.2.2** (`yugabytedb`, `yugabytedb_ycql`) | `yugabytedb/yugabyte:2025.2.2.2-b11` | `cdeadmin-demo-yugabytedb` | `127.0.0.1:55433` (YSQL), `59042` (YCQL), `57000`, `59000` | YSQL: `yugabyte` / DB `cdeadmin_demo`; YCQL: `cassandra` / `<DEMO_PASSWORD>` | Extracts `ycqlsh` + writes `runtime/yugabyte_tools/yb-admin` |
| **Milvus 2.6.5** (`milvus`) | `milvusdb/milvus:v2.6.5` | `cdeadmin-demo-milvus` | `127.0.0.1:59530` (gRPC), `59091` (health) | `root` / `<DEMO_PASSWORD>`, DB `cdeadmin_demo` | Python `pymilvus` client |
| **Milvus etcd** (`milvus` dep) | `quay.io/coreos/etcd:v3.5.18` | `cdeadmin-demo-milvus-etcd` | Internal (`cdeadmin-demo-net:2379`) | Internal metadata store for Milvus | — |
| **MinIO S3 Store** (`milvus` & `tidb_br`) | `minio/minio:RELEASE.2024-12-18T13-15-44Z` | `cdeadmin-demo-milvus-minio`, `cdeadmin-demo-tidb-minio` | Internal (`cdeadmin-demo-net:9000`) | Milvus: `minioadmin`; TiDB BR: `cdeadmin` / `<DEMO_PASSWORD>` | — |
| **PingCAP PD 8.5.6** (`tikv` & `tidb`) | `pingcap/pd:v8.5.6` | `cdeadmin-demo-pd` (TiKV), `cdeadmin-demo-tidb-pd` (TiDB) | `127.0.0.1:52379` -> `2379` (TiKV PD) | Placement Driver for TiKV & TiDB stacks | — |
| **PingCAP TiKV 8.5.6** (`tikv` & `tidb`) | `pingcap/tikv:v8.5.6` | `cdeadmin-demo-tikv`..`-4` (API-v2), `cdeadmin-demo-tidb-store-1`..`-3` (API-v1) | `<host-ip>:52016..52019` (TiKV API-v2 stores) | API-v2 TTL 4-store cluster (`tikv`) + 3-store transactional (`tidb`) | Go builds `runtime/bin/cdeadmin-tikv-helper` |
| **PingCAP TiDB 8.5.6** (`tidb`) | `pingcap/tidb:v8.5.6` | `cdeadmin-demo-tidb` | `127.0.0.1:54000` (SQL), `51000` (status) | `root` (passwordless local), DB `cdeadmin_demo` | MySQL protocol connector |
| **Vitess 23.0.3** (`vitess`) | `vitess/lite:v23.0.3` | `cdeadmin-demo-vitess-*` (`vtctld`, `vtgate`, `vtorc`, 6 `vttablet`s) | `127.0.0.1:15306` (vtgate MySQL), `15000` (vtctld) | `root` (passwordless local), keyspaces `test_keyspace`, `lookup_keyspace` | Generates `runtime/vitess_tools/vtctldclient` |
| **Consul 2.0.3** (`vitess` dep) | `hashicorp/consul:2.0.3` | `cdeadmin-demo-vitess-consul1..3-1` | `127.0.0.1:8500` (UI/API), `8400`, `8600` | 3-node topology server for Vitess Compose stack | — |
| **TiCDC 8.5.6** (`tidb_ticdc`, opt-in) | `pingcap/ticdc:v8.5.6` | `cdeadmin-demo-tidb-ticdc` | `127.0.0.1:58300` -> `8300` | Opt-in changefeed server (requires `dev.sh start tidb` first) | Generates `runtime/tidb_tools/cdc` |
| **PingCAP BR 8.5.6** (`tidb_br`, opt-in) | `pingcap/br:v8.5.6` | Ephemeral CLI container on `cdeadmin-demo-net` | — | Opt-in S3 backup/restore to `s3://tidb-backups/` | Generates `runtime/tidb_tools/br` |
| **TiFlash 8.5.6** (`tidb_tiflash`, opt-in) | `pingcap/tiflash:v8.5.6` | `cdeadmin-demo-tidb-tiflash` | Internal learner store | Opt-in columnar replica (**requires >= 12 GiB Docker RAM**) | — |

> **Embedded Engines (No Docker Image):**
> - **SQLite 3.53.0** (`sqlite`): Built from hash-verified source (`https://www.sqlite.org/2026/sqlite-src-3530000.zip`) by `dev.sh clients` into `tools/reference_engine_demos/runtime/sqlite-3.53.0/`; stores database files in `tools/reference_engine_demos/data/`.
> - **DuckDB 1.5.2** (`duckdb`): Installed via `.venv` (`duckdb==1.5.2`); stores database files in `tools/reference_engine_demos/data/`.

> **Memory Management Tip:** Do **not** run every distributed cluster (`vitess`, `tidb`, `tikv`, `cassandra`, `yugabytedb`, `milvus`, `apache_ignite`, `opensearch`) simultaneously on a 16–32 GiB laptop. Start only the engine(s) you are actively working on, and stop unused clusters with `bash tools/development/dev.sh stop <engine>` or `bash tools/development/dev.sh stop all` (named volumes preserve all data).

---

## 5. Processes for Creating, Seeding & Registering Test Databases

ScratchRobin supports three distinct test-database workflows depending on what you are developing or testing.

### Process A: Provision, Seed & Register the Canonical `cdeadmin_demo` Estate

Every engine has an idempotent native seed adapter (`tools/reference_engine_demos/seed_demo.py`) that populates the standard field-service sample (`customers`, `assets`, `work_orders`, views/functions/indexes/collections/keyspaces).

```bash
# 1. Start, seed, and verify an individual engine (example: PostgreSQL and Firebird)
bash tools/development/dev.sh start postgresql
bash tools/development/dev.sh seed postgresql
bash tools/development/dev.sh verify postgresql

bash tools/development/dev.sh start firebird
bash tools/development/dev.sh seed firebird
bash tools/development/dev.sh verify firebird

# Optional: Prepare & verify ALL 26 profiles sequentially (starts, seeds, verifies,
# and stops each network engine between runs so memory stays bounded):
bash tools/development/dev.sh prepare all

# 2. Preview and register all 26 demo server profiles under your CDEadmin login account
#    (Stop CDEadmin first if it is running; creates an automatic backup of cdeadmin.db)
bash tools/development/dev.sh register --user developer@example.com --dry-run
bash tools/development/dev.sh register --user developer@example.com
```

### Process B: Create New Isolated Test Databases (`dev.sh create-db`)

When developing schema comparison, DDN roundtrip migrations, destructive DDL operations, or custom fixtures, **do not overwrite `cdeadmin_demo`**. Use `bash tools/development/dev.sh create-db` (`tools/reference_engine_demos/create_test_database.py`) to create an isolated test database, optionally seed it with the field-service schema, apply custom SQL/DDL, and register it directly under your ScratchRobin account:

```bash
# 1. Preview what will be created (--dry-run makes zero changes):
bash tools/development/dev.sh create-db \
  --engine postgresql \
  --name dev_erd_roundtrip \
  --seed \
  --register-user developer@example.com \
  --dry-run

# 2. Create a seeded PostgreSQL test database and register it in ScratchRobin:
bash tools/development/dev.sh create-db \
  --engine postgresql \
  --name dev_erd_roundtrip \
  --seed \
  --register-user developer@example.com

# 3. Create an isolated Firebird 5 test database (/var/lib/firebird/data/fb_migration_test.fdb)
#    and apply your own DDL fixture file:
bash tools/development/dev.sh create-db \
  --engine firebird \
  --name fb_migration_test \
  --seed \
  --sql-file /path/to/my_fixture.sql \
  --register-user developer@example.com

# 4. Create isolated embedded SQLite or DuckDB test databases under tools/reference_engine_demos/data/:
bash tools/development/dev.sh create-db --engine sqlite --name local_bi_test --seed
bash tools/development/dev.sh create-db --engine duckdb --name local_cube_test --seed

# 5. Reset (drop & recreate) a disposable test database cleanly:
#    (--drop-existing is strictly blocked on protected/canonical databases like `cdeadmin_demo`)
bash tools/development/dev.sh create-db \
  --engine mariadb \
  --name dev_alter_table_test \
  --drop-existing \
  --seed
```

Supported `--engine` targets for `create-db`:
`sqlite`, `duckdb`, `firebird`, `postgresql`, `cockroachdb`, `yugabytedb`, `mysql`, `mariadb`, `dolt`, `tidb`, `clickhouse`, `mongodb`, `cassandra`, `yugabytedb_ycql`, `opensearch`, `influxdb`.

### Process C: Adding a Brand-New Reference Engine or Canonical Test Fixture to the Repository

When onboarding a new database engine (or adding a new protocol profile) into ScratchRobin's test estate, complete every item in this checklist so portability and CI gates stay green:

1. **Pin Exact Version Metadata** in [engine_versions.json](tools/reference_engine_demos/engine_versions.json):
   - Add `{"engine": "<id>", "product": "<Name>", "version": "<exact-semver>", "deployment": "docker"}` (never `:latest`).
2. **Register the Exact Docker Image(s)** in [docker_images.py](tools/reference_engine_demos/docker_images.py):
   - Add the pinned image tag, container name(s), loopback port mapping (`127.0.0.1:<5xxxx>-><container_port>`), and `bootstrap_client` flag.
3. **Define Container Lifecycle & Protocol Readiness** in [demo_estate.py](tools/reference_engine_demos/demo_estate.py):
   - Add `<id>` to `ENGINE_ORDER`, `CONTAINERS` (or custom multi-node start/stop functions), and `READY_PORTS`.
   - Wait for **actual protocol readiness** (not just an open TCP proxy socket) before returning from `start()`, and attach a named `cdeadmin-demo-<id>` Docker volume so `stop`/`start` retains state.
4. **Extract Matching Native Host Clients (if required)** in [bootstrap.py](tools/reference_engine_demos/bootstrap.py) & [environment.sh](tools/reference_engine_demos/environment.sh):
   - Copy exact-version CLI/shared libraries from `docker create <pinned-image>` into `tools/reference_engine_demos/runtime/<id>/` (never hardcode `/home/<user>` paths).
5. **Add Portable Connection Profile Template** in [connection_profiles.template.json](tools/reference_engine_demos/connection_profiles.template.json) & [register_demo_profiles.py](tools/reference_engine_demos/register_demo_profiles.py):
   - Use `${DEMO_ROOT}` / `${REPOSITORY_ROOT}` placeholders where file paths are needed; never store plaintext passwords in route JSON.
6. **Implement Idempotent Seed, Verify & `create-db` Adapters**:
   - Add `seed_<id>()` and `verify_<id>()` in [seed_demo.py](tools/reference_engine_demos/seed_demo.py) and register in `SEEDERS` / `VERIFIERS`.
   - Add isolated database creation support in [create_test_database.py](tools/reference_engine_demos/create_test_database.py).
7. **Create the Per-Engine Executable Lifecycle Script**:
   - Create `tools/reference_engine_demos/lifecycle/<id>.sh` (`chmod +x`) delegating to `_engine_lifecycle.sh <id> "$@"`.
8. **Run Static Portability & Live Roundtrip Gates**:
   ```bash
   source .venv/bin/activate
   PYTHONPATH=web python3 -m pytest tools/tests/test_reference_engine_demos.py
   make verify TIERS=live ENGINES=<id>
   ```

---

## 6. Running Tests & Verification Gates

Always activate `.venv` and refresh DDN before running tests directly:

```bash
source .venv/bin/activate
bash tools/development/dev.sh ddn

# 1. Product identity & attribution gate (mandatory for UI, docs, runtime, or branding changes):
python3 tools/cdeadmin_product_identity.py --source .
python3 -m unittest tools.tests.test_cdeadmin_product_identity

# 2. Targeted Python unit tests (note PYTHONPATH=web):
PYTHONPATH=web python3 -m pytest tools/tests/test_reference_engine_demos.py

# 3. Targeted Frontend Jest suites:
(cd web && corepack yarn test regression/javascript/cdeadmin/ProjectShell.spec.jsx)

# 4. Unified repository verification runner (`quick`, `unit`, `live`, `browser`):
make verify                               # quick tier (DDN refresh, lint, descriptor & render gates)
make verify TIERS="quick unit"            # + check-gates, Python suites, full Jest suite
make verify TIERS=live ENGINES=postgresql,firebird,mariadb
make verify TIERS=browser                 # headless browser mount verification
```

---

## 7. Quick Troubleshooting Reference

| Error / Symptom | Root Cause & Fix |
| --- | --- |
| `manage.py: error: Run configure first to set application paths.` | Run `bash tools/development/dev.sh configure` and `bash tools/development/dev.sh init` before `dev.sh run` or `dev.sh register`. |
| `chrome-sandbox is not configured correctly ... exited with signal SIGTRAP` | Run `sudo chown root:root runtime/node_modules/electron/dist/chrome-sandbox && sudo chmod 4755 runtime/node_modules/electron/dist/chrome-sandbox`. Never use `--no-sandbox`. |
| `FileNotFoundError` / DDN refresh failure during `dev.sh frontend` or `dev.sh ddn` | Clone `https://github.com/scratchbird-software-inc/Diagram-Design-Notation.git` into `../Diagram-Design-Notation` (or set `SCRATCHROBIN_DDN_SOURCE`). |
| `ModuleNotFoundError: No module named 'config'` when running `pytest` | Prefix direct pytest calls with `PYTHONPATH=web .venv/bin/python3 -m pytest ...`. |
| Server container is `running` in `dev.sh status`, but `cdeadmin_demo` tables are missing | Starting a container only launches the engine; run `bash tools/development/dev.sh seed <engine>` and `verify <engine>`. |
| OpenSearch exits immediately on startup | Check `sysctl vm.max_map_count`; set `sudo sysctl -w vm.max_map_count=262144`. |
| TiFlash refuses to start or TiKV stores get OOM-killed | `tidb_tiflash` requires `>= 12 GiB` Docker memory; stop unused engines first (`bash tools/development/dev.sh stop all`). |
