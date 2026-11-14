# ScratchRobin (CDEadmin) — AI-Executable Full Test Environment Provisioning Guide

> **Target Audience**: Autonomous AI coding agents (and the developers directing them).
> **How to Use**: A developer on a new machine can instruct their AI agent:
> *"Read `docs/AI_AGENT_TEST_ENVIRONMENT_SETUP.md` and set up my ScratchRobin development and test database environment for this machine, including the platform launcher scripts."*

---

## 0. Mandatory AI Agent Guardrails

Before running any command, the AI agent **MUST** enforce these project rules (`AGENTS.md`):

1. **Never run builds, Python, Node, or ScratchRobin as `root` / `Administrator`.** Use `sudo` / elevated prompts *only* for OS package installation, `sysctl vm.max_map_count`, or setting `04755` on Electron's `chrome-sandbox` on Linux (ask the user if interactive elevation is required).
2. **Never pass `--no-sandbox` to Electron** and **never globally weaken PowerShell `ExecutionPolicy`** (use per-invocation `powershell -ExecutionPolicy Bypass -File ...` if needed).
3. **Clone and refresh the mandatory sister repository (`Diagram-Design-Notation`)** before every frontend build and before direct `pytest`, `jest`, or `webpack` runs (`tools/refresh_ddn.py`). Clean temporary DDN intake directories after builds.
4. **Never start all 26 database engines simultaneously.** Distributed fixtures (`vitess`, `tidb`, `tikv`, `cassandra`, `yugabytedb`, `milvus`, `apache_ignite`, `opensearch`) consume substantial RAM. Start, seed, verify, and stop engines sequentially (`prepare all`) or start only the engine(s) requested by the developer.
5. **Preserve existing developer state.** Never overwrite an existing `web/config_local.py` or `~/.cdeadmin/cdeadmin.db` (`%APPDATA%\CDEadmin\cdeadmin.db` on Windows). Always use the built-in `--dry-run` / automatic SQLite backup path when registering profiles.
6. **Never hardcode `/home/<other-user>` paths or commit plaintext credentials.** Demo credentials documented below (`CDEadminDemo-2026!`, `ignite`, `immudb`) apply strictly to loopback-bound (`127.0.0.1`) disposable local test containers.

---

## 1. Host Detection & Platform Decision Matrix

### 1.1 Step 1A — Detect the Host OS, Version, Architecture & Shell

Run the non-destructive inspection command matching your current shell:

- **POSIX Shell (`sh` / `bash` / `zsh` on Linux, WSL2, or macOS)**:
  ```bash
  uname -s -r -m
  test -f /etc/os-release && cat /etc/os-release
  command -v ldd >/dev/null 2>&1 && ldd --version | head -n 1
  command -v sw_vers >/dev/null 2>&1 && sw_vers
  ```
- **PowerShell (`pwsh` 7+ or `powershell.exe` 5.1 on Windows)**:
  ```powershell
  $PSVersionTable.PSVersion
  [System.Environment]::OSVersion.Version
  [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
  wsl.exe --status 2>$null
  wsl.exe --list --verbose 2>$null
  ```

### 1.2 Step 1B — Select the Execution Topology for This Platform

| Detected Host & Version | Architecture | Recommended Full-Estate Topology | Host-Native Option (No Docker/WSL) | Launcher Script Format to Generate |
| :--- | :--- | :--- | :--- | :--- |
| **Ubuntu 24.04 LTS / Debian 13+** (`glibc >= 2.39`, `dpkg-deb` present) | `x86_64` (`amd64`) | **Primary Reference Baseline**: `bash tools/development/dev.sh` + local Docker Engine (`unix:///var/run/docker.sock`). Supports all 26 profiles + automatic MySQL 9.7.0 SDK `.deb` extraction. | Covered directly by `dev.sh` | Bash (`.sh`) — GNU userland (`xdg-open`, `stat -c`) |
| **Ubuntu 22.04 LTS / Debian 12** (`glibc 2.35–2.36`) | `x86_64` (`amd64`) | `bash tools/development/dev.sh` + local Docker Engine, **with one version adjustment**: automatic MySQL 9.7.0 `.deb` SDK extraction requires `glibc >= 2.39`. Supply a host-compatible MySQL C SDK via `export SCRATCHROBIN_MYSQL_CAPI=/abs/path/to/mysql-sdk` **or** run inside an Ubuntu 24.04 Distrobox/container. | — | Bash (`.sh`) — GNU userland |
| **Fedora 40/41+ / RHEL 9+ / Rocky 9+ / Arch Linux** | `x86_64` (`amd64`) | `bash tools/development/dev.sh` + local Docker Engine. Install distro-specific dev headers (§2.1); if `glibc >= 2.39`, install `dpkg` (`dpkg-deb`) so MySQL SDK extraction works, otherwise set `SCRATCHROBIN_MYSQL_CAPI`. | — | Bash (`.sh`) — GNU userland |
| **Windows 11 (23H2/24H2+) or Windows 10 (22H2, build 19045+) / Windows Server 2025** | `x64` (`X64`) | **Mode W-WSL2 (Full 26-Engine Docker Estate)**: Install `Ubuntu-24.04` in WSL2 (`wsl --install -d Ubuntu-24.04`), clone inside WSL2 ext4 (`/home/<user>/src/...`, **never** `/mnt/c/...`), run Docker Engine inside WSL2. Windows 11 WSLg runs Electron natively; Windows 10 uses Web Browser mode (`http://127.0.0.1:5051`) or an X server. | **Mode W-Native (`tools/development/native.py`)**: Pure Windows x64 Python 3.14 + MSVC Build Tools + native Windows Firebird 5.0.4, PostgreSQL 18.3, MySQL 9.7.0, MariaDB 12.2.2, SQLite 3.53.0, DuckDB 1.5.2 (no Docker/WSL). | PowerShell (`.ps1`) compatible with **both** PS 5.1 & PS 7+ (plus `.sh` inside WSL2 if Mode W-WSL2) |
| **Windows on ARM** | `ARM64` | Remote `x86_64` Linux machine via `python tools/development/remote.py` (native Windows ARM64 and ARM64 Linux `.so` extraction are **not** qualified). | Not qualified | PowerShell (`.ps1`) SSH wrapper |
| **macOS 14 Sonoma / macOS 15 Sequoia** | `arm64` (Apple Silicon) or `x86_64` (Intel) | **Mode M-Remote/VM (Full 26-Engine Docker Estate)**: Ubuntu 24.04 `x86_64` VM (Intel Mac) or remote `x86_64` Linux host via `tools/development/remote.py` + `ssh -N -L 127.0.0.1:5051:127.0.0.1:5051`. *(ARM64 Docker Desktop + Rosetta cannot load extracted `x86_64` Linux `.so` clients on macOS host Python.)* | **Mode M-Native (`tools/development/native.sh`)**: Homebrew + Xcode CLT + owned CPython 3.14.8 + native macOS (`arm64` or `x64`) Firebird 5.0.4, PostgreSQL 18.3, MySQL 9.7.0, MariaDB 12.2.2, SQLite 3.53.0, DuckDB 1.5.2. | POSIX Bash/Zsh (`.sh`) — BSD userland (`open`, `stat -f`) |

---

## 2. Platform-Specific Prerequisites & Build Commands

### 2.1 Cloning Both Required Repositories

Clone `CDEadmin` and the public `Diagram-Design-Notation` (`ddn-next-1`) repository side by side:

- **Linux / WSL2 / macOS**:
  ```bash
  mkdir -p ~/src && cd ~/src
  git clone https://github.com/scratchbird-software-inc/CDEadmin.git
  git clone https://github.com/scratchbird-software-inc/Diagram-Design-Notation.git
  cd ~/src/CDEadmin
  ```
  *(In WSL2, verify `pwd` starts with `/home/`, never `/mnt/c/`.)*

- **Native Windows (`PowerShell` — enable long paths if not enabled)**:
  ```powershell
  New-Item -ItemType Directory -Force -Path C:\src | Out-Null
  Set-Location C:\src
  git config --global core.longpaths true
  git clone https://github.com/scratchbird-software-inc/CDEadmin.git
  git clone https://github.com/scratchbird-software-inc/Diagram-Design-Notation.git
  Set-Location C:\src\CDEadmin
  ```

### 2.2 Linux & WSL2 (`x86_64`) System Packages & Toolchain

#### Package installation by Linux distribution

- **Ubuntu 24.04 LTS / Ubuntu 22.04 LTS / Debian 12–13 (`apt`)**:
  ```bash
  sudo apt update
  sudo apt install -y \
    git ca-certificates curl build-essential pkg-config cmake \
    python3 python3-venv python3-dev \
    libpq-dev libkrb5-dev libmariadb-dev libmariadb-dev-compat \
    libssl-dev libffi-dev libsnappy-dev zlib1g-dev libreadline-dev \
    tcl-dev default-jdk libtommath1 libncurses6
  ```
- **Fedora 40/41+ / RHEL 9+ / Rocky 9+ (`dnf`)**:
  ```bash
  sudo dnf install -y \
    git ca-certificates curl gcc gcc-c++ make pkgconf-pkg-config cmake \
    python3 python3-devel \
    libpq-devel krb5-devel mariadb-connector-c-devel \
    openssl-devel libffi-devel snappy-devel zlib-devel readline-devel \
    tcl-devel java-21-openjdk-devel libtommath ncurses-libs dpkg
  ```
- **Arch Linux (`pacman`)**:
  ```bash
  sudo pacman -S --needed \
    git ca-certificates curl base-devel pkgconf cmake \
    python libpqxx postgresql-libs krb5 mariadb-libs \
    openssl libffi snappy zlib readline tcl jdk-openjdk libtommath ncurses dpkg
  ```

#### Required runtime versions (Linux / WSL2)
1. **Docker Engine + Compose v2**: Local `linux/amd64` daemon (`unix:///var/run/docker.sock`). Ensure the developer user is in the `docker` group (`docker info` succeeds without `sudo`).
   - *WSL2 Important Rule*: Run **either** native `dockerd` inside Ubuntu-24.04 (`sudo systemctl enable --now docker`) **or** Docker Desktop WSL2 integration — never both simultaneously. Native `dockerd` inside WSL2 is strongly preferred for multi-IP Cassandra (`127.0.0.1..3`) and 4-store TiKV peer routing.
2. **CPython 3.14** (standard GIL build; never `python3.14t`):
   ```bash
   # Fast option via uv:
   uv python install 3.14
   export SCRATCHROBIN_PYTHON="$(uv python find 3.14)"

   # Reference option (builds CPython 3.14.8 dynamically linked to tracked SQLite 3.53.0):
   bash tools/development/dev.sh interpreter
   export SCRATCHROBIN_PYTHON="$PWD/.native/python/bin/python3.14"
   ```
3. **Node.js 22 LTS + Corepack**: `node --version` >= `v22.x`; run `corepack enable` (do **not** upgrade `yarn.lock`).
4. **Go >= 1.25.5**: Required to compile `cdeadmin-tikv-helper`.
5. **JDK >= 17** (`javac`, `jar`): Compiles Cassandra trigger/JMX auth JARs and Ignite fixture JARs.
6. **OpenSearch Kernel Limit** (if testing OpenSearch):
   ```bash
   [ "$(sysctl -n vm.max_map_count)" -lt 262144 ] && sudo sysctl -w vm.max_map_count=262144
   ```

#### Run Preflight & Build (Linux / WSL2)
```bash
export SCRATCHROBIN_DDN_SOURCE="${SCRATCHROBIN_DDN_SOURCE:-$(cd ../Diagram-Design-Notation && pwd)}"
export SCRATCHROBIN_DDN_WORK="/tmp/sr-ddn-intake"

# 1. Verify prerequisites
bash tools/development/dev.sh doctor

# 2. Build .venv + patched MySQL 9.7.0 & MariaDB 12.2.2 C drivers
bash tools/development/dev.sh python

# 3. Refresh DDN + build production Webpack bundle (default 8192 MB Node heap)
bash tools/development/dev.sh frontend
rm -rf /tmp/sr-ddn-intake

# 4. Pre-pull bootstrap images, compile SQLite 3.53.0 CLI & TiKV Go helper,
#    extract exact native clients, and render runtime/connection_profiles.json
bash tools/development/dev.sh clients

# 5. Install Electron desktop runtime packages & configure Linux SUID sandbox
(cd runtime && corepack yarn install)
sudo chown root:root runtime/node_modules/electron/dist/chrome-sandbox
sudo chmod 4755 runtime/node_modules/electron/dist/chrome-sandbox
```
> **Ubuntu 24.04 AppArmor / Wayland Notes**:
> - Setting `root:root` + `04755` on `runtime/node_modules/electron/dist/chrome-sandbox` satisfies Ubuntu 24.04's `kernel.apparmor_restrict_unprivileged_userns=1` restriction without weakening kernel security or passing `--no-sandbox`.
> - On Wayland desktops with Vulkan driver warnings, Electron runs cleanly under XWayland by default or can be passed `--ozone-platform=x11` if display compositing glitches occur.

---

### 2.3 Native Windows x64 (`Mode W-Native` — PowerShell, No Docker/WSL)

#### Required Windows Prerequisites
- **Windows 10 22H2 (x64), Windows 11 23H2/24H2+ (x64), or Windows Server 2025 (x64)** *(Windows ARM64 is not supported natively)*.
- **Visual Studio 2022 C++ Build Tools** (`Microsoft.VisualStudio.Component.VC.Tools.x86.x64`) + **Windows 10/11 SDK** (`vswhere.exe` auto-detected by `native_assets.py`).
- **Latest Microsoft Visual C++ x64 Redistributable** (must be at least as recent as the MSVC toolset).
- **Standard CPython 3.14 (x64)**, **Node.js 22.22.x (x64)** with `corepack enable`, **Git for Windows**, and **CMake**.
- **PowerShell 5.1 vs PowerShell 7+ (`pwsh`) Note**:
  - Windows 10 and Windows 11 ship `powershell.exe` 5.1 by default, which **does not** support `&&` chaining (until PS 7) and defaults `>` redirection to UTF-16LE. Always execute statements on separate lines with `$ErrorActionPreference = 'Stop'` and use `[System.IO.File]::WriteAllText(..., [System.Text.UTF8Encoding]::new($false))` when generating config files in PowerShell so scripts work identically on PS 5.1 and PS 7+.

#### Run Preflight & Build (Native Windows PowerShell)
```powershell
$ErrorActionPreference = 'Stop'
$Evidence = 'C:\dev-evidence\cdeadmin-native'
$env:SCRATCHROBIN_DDN_SOURCE = 'C:\src\Diagram-Design-Notation'

# Replace `python` with explicit CPython 3.14 path if multiple Pythons are installed
python tools\development\native.py doctor --evidence $Evidence
python tools\development\native.py clients --evidence $Evidence
python tools\development\native.py python --evidence $Evidence
python tools\development\native.py servers --evidence $Evidence
python tools\development\native.py frontend --evidence $Evidence
python tools\development\native.py desktop --evidence $Evidence
```
*(Provisions hash-verified SQLite 3.53.0 + recovery DLL, Firebird 5.0.4 x64 client & embedded/network server, PostgreSQL 18.3 x64 binaries, MariaDB Connector/C 3.4.8 + patched Python wheel, MySQL 9.7.0 + MySQL Shell 9.7.0, MariaDB 12.2.2, and ScratchBird pure-Python wire SDK under `.native\`.)*

---

### 2.4 Native macOS (`Mode M-Native` — Sonoma 14 / Sequoia 15, Apple Silicon `arm64` & Intel `x86_64`)

```bash
xcode-select --install 2>/dev/null || true
brew install libpq openssl@3 krb5 pkg-config cmake bison icu4c libxml2 lz4 zstd readline zlib node@22

# Note: Homebrew prefix is /opt/homebrew on Apple Silicon (arm64) and /usr/local on Intel (x86_64);
# tools/development/native.py resolves `brew --prefix` automatically.
export SCRATCHROBIN_PYTHON=/absolute/path/to/python3.14
export SCRATCHROBIN_DDN_SOURCE="$HOME/src/Diagram-Design-Notation"
EVIDENCE="$HOME/dev-evidence/cdeadmin-native"

bash tools/development/native.sh doctor --evidence "$EVIDENCE"
bash tools/development/native.sh clients --evidence "$EVIDENCE"
bash tools/development/native.sh python --evidence "$EVIDENCE"
bash tools/development/native.sh servers --evidence "$EVIDENCE"
bash tools/development/native.sh frontend --evidence "$EVIDENCE"
bash tools/development/native.sh desktop --evidence "$EVIDENCE"
```

---

## 3. Complete Docker Image Manifest to Download (Linux / WSL2 Estate)

All 29 Docker images in the reference estate are strictly version-pinned in `tools/reference_engine_demos/docker_images.py`.

### 3.1 Automated Image Check & Pull Commands

```bash
# Inspect local cache status (present vs missing) for all 29 images:
bash tools/development/dev.sh images

# Download groups depending on available disk & bandwidth:
bash tools/development/dev.sh pull bootstrap              # 7 images required by `dev.sh clients`
bash tools/development/dev.sh pull local                  # 4 fast local engines (firebird, redis, mongodb, cassandra)
bash tools/development/dev.sh pull core                   # 14 single-container SQL & NoSQL servers
bash tools/development/dev.sh pull <engine_id>            # Pull images for one engine (e.g. firebird, postgresql, tidb)
bash tools/development/dev.sh pull all                    # All 26 standard reference-estate images
bash tools/development/dev.sh pull all --include-opt-in   # All 29 images (adds TiDB TiCDC, BR, TiFlash)
```

### 3.2 All 29 Pinned Docker Images

| # | Exact Docker Image | Engine Profile(s) | Group(s) | Container Name(s) | Host Loopback Port Mapping(s) | Host Client Extracted? |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `postgres:18.3` | `postgresql` | `core`, `all` | `cdeadmin-demo-postgresql` | `127.0.0.1:55432->5432` | No (uses host `libpq`) |
| 2 | `firebirdsql/firebird:5.0.4` | `firebird` | `bootstrap`, `local`, `core`, `all` | `cdeadmin-demo-firebird` | `127.0.0.1:53050->3050` | **Yes** (`libfbclient.so.5.0.4`) |
| 3 | `mysql:9.7.0` | `mysql` | `bootstrap`, `core`, `all` | `cdeadmin-demo-mysql` | `127.0.0.1:53306->3306` | **Yes** (`mysqlsh` 9.7.0 + private OpenSSL 3.5.1) |
| 4 | `mariadb:12.2.2` | `mariadb` | `bootstrap`, `core`, `all` | `cdeadmin-demo-mariadb` | `127.0.0.1:53307->3306` | **Yes** (`mariadb`, `mariadb-dump`, `mariadb-upgrade`, `mariadb-binlog`, `mariadb-admin`) |
| 5 | `redis:8.6.2` | `redis` | `local`, `core`, `all` | `cdeadmin-demo-redis` | `127.0.0.1:56379->6379` | No |
| 6 | `mongo:8.2.6` | `mongodb` | `local`, `core`, `all` | `cdeadmin-demo-mongodb` | `127.0.0.1:57017->27017` | No |
| 7 | `clickhouse/clickhouse-server:25.12.10.7` | `clickhouse` | `core`, `all` | `cdeadmin-demo-clickhouse` | `127.0.0.1:58123->8123`, `59001->9000` | No |
| 8 | `cockroachdb/cockroach:v26.1.3` | `cockroachdb` | `core`, `all` | `cdeadmin-demo-cockroachdb` | `127.0.0.1:56257->26257`, `58081->8080` | Wrapper (`cockroach`) |
| 9 | `dolthub/dolt-sql-server:1.86.6` | `dolt` | `core`, `all` | `cdeadmin-demo-dolt` | `127.0.0.1:53308->3306` | No |
| 10 | `codenotary/immudb:1.11.0` | `immudb` | `core`, `all` | `cdeadmin-demo-immudb` | `127.0.0.1:53322->3322`, `55435->5432`, `58082->8080`, `59497->9497` | No |
| 11 | `influxdb:3.9.0-core` | `influxdb` | `core`, `all` | `cdeadmin-demo-influxdb` | `127.0.0.1:58181->8181` | No |
| 12 | `neo4j:2026.04.0-enterprise` | `neo4j` | `core`, `all` | `cdeadmin-demo-neo4j` | `127.0.0.1:57687->7687`, `57474->7474` | Bind-mounted admin wrapper |
| 13 | `opensearchproject/opensearch:3.6.0` | `opensearch`, `opensearch_sql_ppl` | `core`, `all` | `cdeadmin-demo-opensearch` | `127.0.0.1:59200->9200`, `59600->9600` | No |
| 14 | `ghcr.io/xtdb/xtdb:2.1.0` | `xtdb` | `core`, `all` | `cdeadmin-demo-xtdb` | `127.0.0.1:55434->5432`, `58083->8080` | No |
| 15 | `apacheignite/ignite:2.17.0` | `apache_ignite` | `bootstrap`, `all` | `cdeadmin-demo-apache-ignite`, `...-2` | `127.0.0.1:51080->10800`, `58080->8080` | **Yes** (Ignite JARs for fixture build) |
| 16 | `cassandra:5.0.8` | `cassandra` | `bootstrap`, `local`, `all` | `cdeadmin-demo-cassandra`, `...-2`, `...-3` | `127.0.0.1..3:19042->19042`, `127.0.0.1..3:17199->17199` | **Yes** (`cqlsh`, `nodetool`, `sstableloader` + JARs) |
| 17 | `foundationdb/foundationdb:7.3.77` | `foundationdb` | `bootstrap`, `all` | `cdeadmin-demo-foundationdb` | `127.0.0.1:54500..54503->54500..54503` | **Yes** (`fdbcli`, `fdbbackup`, `fdbrestore`, `libfdb_c.so`) |
| 18 | `yugabytedb/yugabyte:2025.2.2.2-b11` | `yugabytedb`, `yugabytedb_ycql` | `bootstrap`, `all` | `cdeadmin-demo-yugabytedb` | `127.0.0.1:55433->5433`, `59042->9042`, `57000->7000`, `59000->9000` | **Yes** (`ycqlsh` + `yb-admin` wrapper) |
| 19 | `milvusdb/milvus:v2.6.5` | `milvus` | `all` | `cdeadmin-demo-milvus` | `127.0.0.1:59530->19530`, `59091->9091` | No |
| 20 | `quay.io/coreos/etcd:v3.5.18` | `milvus` *(dep)* | `all` | `cdeadmin-demo-milvus-etcd` | Internal (`cdeadmin-demo-net:2379`) | No |
| 21 | `minio/minio:RELEASE.2024-12-18T13-15-44Z` | `milvus` *(dep)* & `tidb_br` | `all` | `cdeadmin-demo-milvus-minio`, `cdeadmin-demo-tidb-minio` | Internal (`cdeadmin-demo-net:9000`) | No |
| 22 | `pingcap/pd:v8.5.6` | `tikv`, `tidb` | `all` | `cdeadmin-demo-pd`, `cdeadmin-demo-tidb-pd` | `127.0.0.1:52379->2379` (TiKV PD) | No |
| 23 | `pingcap/tikv:v8.5.6` | `tikv`, `tidb` | `all` | `cdeadmin-demo-tikv`..`-4` & `cdeadmin-demo-tidb-store-1`..`-3` | `<host-ip>:52016..52019` (API-v2) | Go builds `cdeadmin-tikv-helper` |
| 24 | `pingcap/tidb:v8.5.6` | `tidb` | `all` | `cdeadmin-demo-tidb` | `127.0.0.1:54000->4000`, `51000->10080` | No |
| 25 | `vitess/lite:v23.0.3` | `vitess` | `all` | `cdeadmin-demo-vitess-*` (`vtgate`, `vtctld`, `vtorc`, `vttablet`s) | `127.0.0.1:15306->15306`, `15099`, `15000` | Wrapper (`vtctldclient`) |
| 26 | `hashicorp/consul:2.0.3` | `vitess` *(dep)* | `all` | `cdeadmin-demo-vitess-consul1..3-1` | `127.0.0.1:8500`, `8400`, `8600` | No |
| 27 | `pingcap/ticdc:v8.5.6` | `tidb_ticdc` *(opt-in)* | `opt-in` | `cdeadmin-demo-tidb-ticdc` | `127.0.0.1:58300->8300` | Wrapper (`cdc`) |
| 28 | `pingcap/br:v8.5.6` | `tidb_br` *(opt-in)* | `opt-in` | Ephemeral CLI on `cdeadmin-demo-net` | — | Wrapper (`br`) |
| 29 | `pingcap/tiflash:v8.5.6` | `tidb_tiflash` *(opt-in)* | `opt-in` | `cdeadmin-demo-tidb-tiflash` | Internal *(requires >= 12 GiB Docker RAM)* | No |

*(Embedded engines `sqlite` 3.53.0 and `duckdb` 1.5.2 run directly against local files in `tools/reference_engine_demos/data/` and use no Docker container.)*

---

## 4. Complete Users, Roles & Passwords Across All Engines

### 4.1 Three Distinct Credential Layers (Do Not Conflate)

1. **ScratchRobin Desktop / Single-User Web Mode (`PGADMIN_SERVER_MODE=OFF`)**:
   - **No login prompt**. Internally uses built-in account `cdeadmin@localhost` stored in `~/.cdeadmin/cdeadmin.db` (Linux), `~/Library/Application Support/cdeadmin/cdeadmin.db` (macOS), or `%APPDATA%\CDEadmin\cdeadmin.db` (Windows).
2. **ScratchRobin Multi-User Server Mode (`SERVER_MODE = True` via `web/config_local.py`)**:
   - Created interactively during `bash tools/development/dev.sh init` (e.g., `developer@example.com` + personal password), stored in `.devstate/application/cdeadmin.db`.
3. **Database Engine Test Credentials** (below):
   - Used when ScratchRobin connects to each database engine. When saving a database password inside ScratchRobin, the user may be prompted once to set a **ScratchRobin Master Password** that encrypts stored connection secrets.

### 4.2 Master Reference Table — Users, Roles & Passwords per Engine

> **Standard Demo Password**: **`CDEadminDemo-2026!`** unless noted otherwise in the **Password / Auth** column.

| Engine Profile | Host & Port(s) | Default Database / Path | Username(s) | Roles / Privileges | Password / Auth |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Apache Cassandra** (`cassandra`) | `127.0.0.1..3:19042` (CQL)<br>`127.0.0.1..3:17199` (JMX) | `cdeadmin_demo` | `cassandra` *(both CQL & JMX)* | CQL `SUPERUSER = true`; JMX read/write admin | `CDEadminDemo-2026!` *(unseeded container starts with `cassandra` until `seed` alters it)* |
| **Apache Ignite** (`apache_ignite`) | Thin: `127.0.0.1:51080`<br>REST: `127.0.0.1:58080` | *(cluster caches)* | `ignite` | Cluster administrator (`control.sh` & Thin/REST) | `ignite` |
| **ClickHouse** (`clickhouse`) | HTTP: `127.0.0.1:58123`<br>Native: `127.0.0.1:59001` | `cdeadmin_demo` | `cdeadmin_demo` | `ACCESS MANAGEMENT = 1` (can `CREATE USER`/`ROLE`/`GRANT`) | `CDEadminDemo-2026!` |
| **CockroachDB** (`cockroachdb`) | SQL: `127.0.0.1:56257`<br>HTTP: `127.0.0.1:58081` | `cdeadmin_demo` | `root` | `admin` role (`--insecure` single-node) | *(None — passwordless, `sslmode=disable`)* |
| **Dolt** (`dolt`) | `127.0.0.1:53308` | `cdeadmin_demo` | `root` | Superuser (`root@%`) | *(None — blank password)* |
| **DuckDB** (`duckdb`) | *(Embedded file)* | `<DEMO_ROOT>/data/cdeadmin_demo.duckdb` | *(OS user)* | Local file owner | *(None — file-based)* |
| **Firebird 5.0** (`firebird`) | `127.0.0.1:53050` | `/var/lib/firebird/data/cdeadmin_demo.fdb`<br>*(Create root: `/var/lib/firebird/data`)* | `SYSDBA` | Server/Services admin (`security5.fdb`), `RDB$ADMIN`, plus seeded SQL role `CDEADMIN_OPERATOR` | `CDEadminDemo-2026!` |
| **FoundationDB** (`foundationdb`) | `127.0.0.1:54500..54503` | `default` | *(Cluster file)* | Full cluster control via `<DEMO_ROOT>/runtime/fdb.cluster` | *(None — cluster token inside `fdb.cluster`)* |
| **immudb** (`immudb`) | PGSQL: `127.0.0.1:55435`<br>gRPC: `53322` · HTTP: `58082` | `cdeadmin_demo` *(+ `defaultdb`)* | `immudb` | Global `SYS_ADMIN` | `immudb` |
| **InfluxDB 3 Core** (`influxdb`) | `127.0.0.1:58181` | `cdeadmin_demo` | *(None)* | `--without-auth` local mode | *(None — `disabled_local_demo`)* |
| **MariaDB 12.2** (`mariadb`) | `127.0.0.1:53307` | `cdeadmin_demo` | `cdeadmin_demo`<br>`root` | `cdeadmin_demo`: full DB privileges<br>`root`: global DBA / superuser | `CDEadminDemo-2026!` *(same password for both users)* |
| **Milvus** (`milvus`) | `127.0.0.1:59530` | `cdeadmin_demo` *(+ `default`)* | `root` | Cluster `admin` (`authorizationEnabled=true`) | `CDEadminDemo-2026!` *(SDK token: `root:CDEadminDemo-2026!`)* |
| **MongoDB** (`mongodb`) | `127.0.0.1:57017` | `cdeadmin_demo` | *(None)* | Unauthenticated local fixture | *(None)* |
| **MySQL 9.7** (`mysql`) | `127.0.0.1:53306` | `cdeadmin_demo` | `cdeadmin_demo`<br>`root` | `cdeadmin_demo`: full DB privileges<br>`root`: global `SYSTEM_USER` / DBA | `CDEadminDemo-2026!` *(same password for both users)* |
| **Neo4j Enterprise** (`neo4j`) | Bolt: `127.0.0.1:57687`<br>HTTP: `127.0.0.1:57474` | `neo4j` *(+ `system`)* | `neo4j` | Enterprise RBAC: `admin` *(built-in roles: `admin`, `architect`, `publisher`, `editor`, `reader`, `PUBLIC`)* | `CDEadminDemo-2026!` |
| **OpenSearch** (`opensearch`, `opensearch_sql_ppl`) | `127.0.0.1:59200` | Index: `cdeadmin-work-orders` | *(None)* | `DISABLE_SECURITY_PLUGIN=true` | *(None)* |
| **PostgreSQL 18** (`postgresql`) | `127.0.0.1:55432` | `cdeadmin_demo` | `cdeadmin_demo` | Bootstrap cluster `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `LOGIN` *(note: initialized with `POSTGRES_USER=cdeadmin_demo`, not `postgres`)* | `CDEadminDemo-2026!` |
| **Redis** (`redis`) | `127.0.0.1:56379` | DB `0` | `default` | Full ACL (`+@all ~*`) | *(None)* |
| **SQLite 3.53** (`sqlite`) | *(Embedded file)* | `<DEMO_ROOT>/data/cdeadmin_demo.sqlite` | *(OS user)* | Local file owner | *(None — file-based)* |
| **TiDB** (`tidb`) | SQL: `127.0.0.1:54000`<br>HTTP: `127.0.0.1:51000` | `cdeadmin_demo` | `root` | `root@%` superuser | *(None — blank password)* |
| **TiDB BR MinIO** (`tidb_br`, opt-in) | S3: `127.0.0.1:9000` | Bucket: `tidb-backups` | `cdeadmin` | MinIO root admin | `CDEadminDemo-2026!` |
| **TiKV** (`tikv`) | PD: `127.0.0.1:52379` | `default` *(API v2)* | *(None)* | Local PD/TiKV gRPC | *(None)* |
| **Vitess** (`vitess`) | VTGate: `127.0.0.1:15306`<br>HTTP: `127.0.0.1:15099` | `test_keyspace`, `lookup_keyspace` | `root` | Local VTGate user | *(None — blank password)* |
| **XTDB 2** (`xtdb`) | PG wire: `127.0.0.1:55434`<br>HTTP: `127.0.0.1:58083` | `xtdb` | `xtdb` | Default XTDB user | *(None — blank password)* |
| **YugabyteDB YSQL** (`yugabytedb`) | `127.0.0.1:55433` | `cdeadmin_demo` | `yugabyte` | YSQL `SUPERUSER` | *(None — passwordless local YSQL)* |
| **YugabyteDB YCQL** (`yugabytedb_ycql`) | `127.0.0.1:59042` | `cdeadmin_demo` | `cassandra` | YCQL `SUPERUSER` (`--use_cassandra_authentication=true`) | `CDEadminDemo-2026!` *(altered from `cassandra` during `seed`)* |

---

## 5. Creating, Seeding & Registering Test / Example Databases

### 5.1 Canonical Sample Estate (`cdeadmin_demo` — Field-Service Dataset)

Every engine has an idempotent native seeder (`tools/reference_engine_demos/seed_demo.py`) and round-trip verifier:

```bash
# Seed and verify specific engines (recommended everyday workflow):
for eng in sqlite duckdb firebird postgresql mysql mariadb redis mongodb; do
  bash tools/development/dev.sh start "$eng"
  bash tools/development/dev.sh seed "$eng"
  bash tools/development/dev.sh verify "$eng"
done

# Or seed and verify ALL 26 engine profiles sequentially
# (automatically stops heavy network containers between engines to bound RAM):
bash tools/development/dev.sh prepare all
```

### 5.2 Registering All 26 Demo Profiles into ScratchRobin

Stop ScratchRobin before running profile registration (the script creates a timestamped online SQLite backup of `cdeadmin.db` first).

- **Option A — Electron Desktop & Single-User Web Mode (`~/.cdeadmin/cdeadmin.db`, user `cdeadmin@localhost`)**:
  *(Ensure ScratchRobin has been launched at least once so `~/.cdeadmin/cdeadmin.db` is initialized, then stop it and run:)*
  ```bash
  source tools/reference_engine_demos/environment.sh
  PGADMIN_SERVER_MODE=OFF .venv/bin/python tools/reference_engine_demos/register_demo_profiles.py \
    --user cdeadmin@localhost --dry-run
  PGADMIN_SERVER_MODE=OFF .venv/bin/python tools/reference_engine_demos/register_demo_profiles.py \
    --user cdeadmin@localhost
  ```
- **Option B — Multi-User Server Mode (`web/config_local.py` -> `.devstate/application/cdeadmin.db`)**:
  ```bash
  bash tools/development/dev.sh configure
  bash tools/development/dev.sh init   # interactive: creates your <email> account
  bash tools/development/dev.sh register --user developer@example.com --dry-run
  bash tools/development/dev.sh register --user developer@example.com
  ```

### 5.3 Creating Additional Isolated Test Databases (`create_test_database.py`)

When testing destructive DDL, schema diff, or DDN roundtrips, create isolated databases instead of modifying `cdeadmin_demo`:

```bash
# Server Mode (uses web/config_local.py):
bash tools/development/dev.sh create-db \
  --engine firebird \
  --name fb_roundtrip_test \
  --seed \
  --register-user developer@example.com

# Desktop / Single-User Web Mode (uses ~/.cdeadmin/cdeadmin.db):
source tools/reference_engine_demos/environment.sh
PGADMIN_SERVER_MODE=OFF .venv/bin/python tools/reference_engine_demos/create_test_database.py \
  --engine firebird \
  --name fb_roundtrip_test \
  --seed \
  --register-user cdeadmin@localhost
```
*(Supported `--engine` values: `sqlite`, `duckdb`, `firebird`, `postgresql`, `cockroachdb`, `yugabytedb`, `mysql`, `mariadb`, `dolt`, `tidb`, `clickhouse`, `mongodb`, `cassandra`, `yugabytedb_ycql`, `opensearch`, `influxdb`. Pass `--sql-file <path.sql>` to apply custom DDL or `--drop-existing` to reset a non-protected test DB.)*

### 5.4 Native Windows / macOS Loopback Test Fixtures (`Mode W-Native` / `Mode M-Native`)

On host-native Windows or macOS without Docker, run the `fixtures` stage to spin up temporary, owned, loopback-only PostgreSQL 18.3, MySQL 9.7.0, MariaDB 12.2.2, Firebird 5.0.4, SQLite 3.53.0, and DuckDB 1.5.2 instances and run their live qualification gates:

- **Windows PowerShell**: `python tools\development\native.py fixtures --evidence C:\dev-evidence\cdeadmin-native-fixtures`
- **macOS**: `bash tools/development/native.sh fixtures --evidence "$HOME/dev-evidence/cdeadmin-native-fixtures"`

---

## 6. Generating Platform-Specific Developer Workspace Scripts

As the final provisioning step, the AI agent **MUST** create a developer-designated workspace control folder (outside the git checkout — e.g. `~/scratchrobin-workspace/` on Linux/macOS/WSL2 or `C:\src\scratchrobin-workspace\` on Windows, or any path requested by the developer) containing:

1. **Quick application launchers for BOTH the Electron Desktop app and the Normal Web Browser app**, supporting `start`, `stop`, `status`, `restart`, and `build`.
2. **Per-engine test environment scripts** (e.g., `firebird.sh` / `firebird.ps1`) supporting `start`, `stop`, and `status` (plus `restart`, `seed`, `verify`, `test`), along with an `engines` overview script (`engines.sh` / `engines.ps1`).
3. A copy or link to the human-readable credential reference (`ENGINE_CREDENTIALS.md` from §4.2).

Choose **Section 6.1** for Linux / macOS / WSL2 (`bash` / POSIX) or **Section 6.2** for Windows (`PowerShell` 5.1 & 7+).

---

### 6.1 Linux & macOS Bash Scripts (`.sh` — Portable Across GNU Linux & BSD macOS)

Set `WORKSPACE_DIR` and `CDEADMIN_ROOT` (and `DDN_SOURCE`) to the developer's actual paths before writing these files, then `chmod +x "$WORKSPACE_DIR"/*.sh`.

#### A. `$WORKSPACE_DIR/start_robin.sh` (plus `start_robin_electron.sh` & `start_robin_web.sh`)

```bash
#!/usr/bin/env bash
# Launch & manage ScratchRobin in Electron Desktop mode or Normal Web Browser mode.
# Usage:
#   ./start_robin.sh                         Start Electron desktop on latest build
#   ./start_robin.sh electron {start|stop|status|restart|build}
#   ./start_robin.sh web {start|stop|status|restart|open|build} [--port N] [--no-open]
#   ./start_robin.sh {status|stop|build|build-only}
set -euo pipefail

CDEADMIN_ROOT="${CDEADMIN_ROOT:-$HOME/src/CDEadmin}"
DDN_SOURCE_DEFAULT="${SCRATCHROBIN_DDN_SOURCE:-$(cd "$CDEADMIN_ROOT/../Diagram-Design-Notation" 2>/dev/null && pwd || echo "$HOME/src/Diagram-Design-Notation")}"
DDN_WORK_DEFAULT="${SCRATCHROBIN_DDN_WORK:-/tmp/sr-ddn-intake}"
BUNDLE_FILE="$CDEADMIN_ROOT/web/pgadmin/static/js/generated/app.bundle.js"
ELECTRON_LOG="${SCRATCHROBIN_ELECTRON_LOG:-/tmp/scratchrobin-electron.log}"
WEB_LOG="${SCRATCHROBIN_WEB_LOG:-/tmp/scratchrobin-web.log}"
WEB_PORT_DEFAULT="${SCRATCHROBIN_WEB_PORT:-5051}"
WEB_STATE_FILE="/tmp/scratchrobin-web.state"

file_mtime() {
    if stat -c '%y' "$1" >/dev/null 2>&1; then
        stat -c '%y' "$1"          # GNU coreutils (Linux)
    else
        stat -f '%Sm' "$1"         # BSD stat (macOS)
    fi
}

open_url() {
    local url="$1"
    if [[ "$(uname -s)" == "Darwin" ]]; then
        open "$url" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
        nohup xdg-open "$url" >/dev/null 2>&1 </dev/null &
    fi
}

load_env() {
    [[ -f "$CDEADMIN_ROOT/.venv/bin/activate" ]] && source "$CDEADMIN_ROOT/.venv/bin/activate"
    if [[ "$(uname -s)" == "Linux" && -f "$CDEADMIN_ROOT/tools/reference_engine_demos/environment.sh" ]]; then
        source "$CDEADMIN_ROOT/tools/reference_engine_demos/environment.sh"
    fi
}

find_electron_pids() {
    pgrep -f "$CDEADMIN_ROOT/runtime/node_modules/electron" || true
}

find_web_pids() {
    local all_pids epids
    all_pids=$(pgrep -f "$CDEADMIN_ROOT/web/CDEadmin\\.py" || true)
    [[ -z "$all_pids" ]] && return 0
    epids=$(find_electron_pids)
    while read -r pid; do
        [[ -z "$pid" ]] && continue
        local ppid
        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ' || true)
        if [[ -n "$epids" ]] && echo "$epids" | grep -qx "$ppid"; then continue; fi
        echo "$pid"
    done <<< "$all_pids"
}

active_web_url() {
    local port="$WEB_PORT_DEFAULT"
    [[ -f "$WEB_STATE_FILE" ]] && port=$(cat "$WEB_STATE_FILE" 2>/dev/null || echo "$WEB_PORT_DEFAULT")
    echo "http://127.0.0.1:${port}"
}

build_bundle() {
    load_env
    export SCRATCHROBIN_DDN_SOURCE="$DDN_SOURCE_DEFAULT"
    export SCRATCHROBIN_DDN_WORK="$DDN_WORK_DEFAULT"
    local heap="${CDEADMIN_NODE_HEAP_MB:-6144}"
    (
        cd "$CDEADMIN_ROOT/web"
        NODE_ENV=production NODE_OPTIONS="--max-old-space-size=${heap}" corepack yarn webpacker
        corepack yarn git:hash
    )
    rm -rf "$DDN_WORK_DEFAULT"
}

ensure_bundle() {
    [[ -f "$BUNDLE_FILE" ]] || build_bundle
}

stop_pids() {
    local label="$1" pids="$2"
    [[ -z "$pids" ]] && { echo "$label is not running."; return 0; }
    echo "Stopping $label..."
    while read -r p; do [[ -n "$p" ]] && kill "$p" 2>/dev/null || true; done <<< "$pids"
    for _ in {1..20}; do
        local alive=""
        while read -r p; do [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null && alive="$alive $p"; done <<< "$pids"
        [[ -z "$alive" ]] && break
        sleep 0.25
    done
    while read -r p; do [[ -n "$p" ]] && kill -9 "$p" 2>/dev/null || true; done <<< "$pids"
    echo "$label stopped."
}

start_electron() {
    ensure_bundle
    load_env
    echo "Starting ScratchRobin (Electron Desktop) — bundle: $(file_mtime "$BUNDLE_FILE")"
    (
        cd "$CDEADMIN_ROOT/runtime"
        nohup corepack yarn start >"$ELECTRON_LOG" 2>&1 </dev/null &
        echo "Electron PID : $! (log: $ELECTRON_LOG)"
    )
}

start_web() {
    local port="$1" auto_open="$2"
    ensure_bundle
    load_env
    local existing
    existing=$(find_web_pids)
    if [[ -n "$existing" ]]; then
        local url
        url=$(active_web_url)
        echo "ScratchRobin Web is already running at $url"
        [[ "$auto_open" == "true" ]] && open_url "$url"
        return 0
    fi
    echo "$port" > "$WEB_STATE_FILE"
    local url="http://127.0.0.1:${port}"
    (
        cd "$CDEADMIN_ROOT/web"
        PGADMIN_SERVER_MODE=OFF PGADMIN_INT_PORT="$port" \
            nohup "$CDEADMIN_ROOT/.venv/bin/python" "$CDEADMIN_ROOT/web/CDEadmin.py" \
            >"$WEB_LOG" 2>&1 </dev/null &
        echo "Web Server PID : $! (log: $WEB_LOG)"
    )
    for _ in {1..40}; do
        if curl -fsS -o /dev/null "$url/browser/" 2>/dev/null; then
            echo "ScratchRobin Web is ready at: $url"
            [[ "$auto_open" == "true" ]] && open_url "$url"
            return 0
        fi
        sleep 0.4
    done
    echo "Warning: Web server did not respond in time; inspect $WEB_LOG" >&2
    exit 1
}

mode="electron"; action="start"; auto_open="true"; web_port="$WEB_PORT_DEFAULT"
if [[ $# -gt 0 ]]; then
    case "$1" in
        electron|desktop) mode="electron"; shift; [[ $# -gt 0 && "$1" != --* ]] && { action="$1"; shift; } ;;
        web|browser)      mode="web";      shift; [[ $# -gt 0 && "$1" != --* ]] && { action="$1"; shift; } ;;
        start)            mode="electron"; action="start"; shift ;;
        stop|status|restart|build|build-only) mode="both"; action="$1"; shift ;;
    esac
fi
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-open) auto_open="false" ;;
        --port) shift; web_port="${1:-$WEB_PORT_DEFAULT}" ;;
    esac
    shift || true
done

case "$action" in
    start)      [[ "$mode" == "web" ]] && start_web "$web_port" "$auto_open" || start_electron ;;
    stop)       [[ "$mode" != "web" ]] && stop_pids "Electron" "$(find_electron_pids)"
                [[ "$mode" != "electron" ]] && { stop_pids "Web" "$(find_web_pids)"; rm -f "$WEB_STATE_FILE"; } ;;
    restart)    "$0" "$mode" stop; "$0" "$mode" start --port "$web_port" $([[ "$auto_open" == "false" ]] && echo "--no-open") ;;
    open)       open_url "$(active_web_url)" ;;
    build)      build_bundle; [[ "$mode" == "web" ]] && start_web "$web_port" "$auto_open" || start_electron ;;
    build-only) build_bundle ;;
    status)
        [[ -f "$BUNDLE_FILE" ]] && echo "Bundle built     : $(file_mtime "$BUNDLE_FILE")" || echo "Bundle built     : MISSING"
        [[ "$mode" != "web" ]] && echo "Electron desktop : $([[ -n "$(find_electron_pids)" ]] && echo "RUNNING" || echo "STOPPED")"
        [[ "$mode" != "electron" ]] && echo "Web browser mode : $([[ -n "$(find_web_pids)" ]] && echo "RUNNING ($(active_web_url))" || echo "STOPPED")"
        ;;
esac
```

Create the two companion wrappers alongside `start_robin.sh`:
- `start_robin_electron.sh`:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  exec "$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/start_robin.sh" electron "$@"
  ```
- `start_robin_web.sh`:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  exec "$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/start_robin.sh" web "$@"
  ```

#### B. `$WORKSPACE_DIR/_engine_ctl.sh` and `<engine>.sh` (`start | stop | status`)

Create `_engine_ctl.sh` delegating to `$CDEADMIN_ROOT/.venv/bin/python "$CDEADMIN_ROOT/tools/reference_engine_demos/demo_estate.py"` with `$CDEADMIN_ROOT/tools/reference_engine_demos/environment.sh` sourced, then generate an executable `<engine>.sh` wrapper for each of the 26 engine IDs (`apache_ignite`, `cassandra`, `clickhouse`, `cockroachdb`, `dolt`, `duckdb`, `firebird`, `foundationdb`, `immudb`, `influxdb`, `mariadb`, `milvus`, `mongodb`, `mysql`, `neo4j`, `opensearch`, `opensearch_sql_ppl`, `postgresql`, `redis`, `sqlite`, `tidb`, `tikv`, `vitess`, `xtdb`, `yugabytedb`, `yugabytedb_ycql`) plus opt-in `tidb_ticdc`, `tidb_br`, `tidb_tiflash`:

```bash
#!/usr/bin/env bash
# Template for <engine>.sh (replace <engine> with e.g. firebird)
set -euo pipefail
script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "$script_dir/_engine_ctl.sh" "<engine>" "$@"
```

---

### 6.2 Windows PowerShell Scripts (`.ps1` — Compatible with PowerShell 5.1 & PowerShell 7+)

> **Windows Compatibility Rules for AI Agents**:
> - Never use `&&` in `.ps1` files so Windows PowerShell 5.1 (`powershell.exe`) parses them cleanly alongside PowerShell 7 (`pwsh.exe`).
> - Support **both** Windows topologies automatically:
>   - If `$WslDistribution` / `$WslRepoPath` is configured (`Mode W-WSL2`), engine lifecycle commands dispatch to `wsl.exe --distribution Ubuntu-24.04 --cd $WslRepoPath --exec bash ...` and Web Browser mode opens `http://127.0.0.1:5051` in the native Windows browser via `Start-Process`!
>   - If `$NativeRepoPath` is configured (`Mode W-Native`), Electron (`runtime\node_modules\.bin\electron.cmd`) and Web (`web\CDEadmin.py` under `.venv\Scripts\python.exe`) run directly on native Windows!

#### A. `start_robin.ps1` (plus `start_robin_electron.ps1` & `start_robin_web.ps1`)

```powershell
# Launch & manage ScratchRobin on Windows (Electron Desktop & Web Browser modes).
# Compatible with Windows PowerShell 5.1 and PowerShell 7+.
# Usage:
#   .\start_robin.ps1                              # Start Electron desktop
#   .\start_robin.ps1 electron start|stop|status
#   .\start_robin.ps1 web start|stop|status|open
#   .\start_robin.ps1 status|stop|build
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$ModeOrAction = 'electron',
    [Parameter(Position = 1)][string]$Action = 'start',
    [int]$Port = 5051,
    [switch]$NoOpen,
    [string]$NativeRepoPath = 'C:\src\CDEadmin',
    [string]$DdnSourcePath = 'C:\src\Diagram-Design-Notation',
    [string]$WslDistribution = '',
    [string]$WslRepoPath = ''
)
$ErrorActionPreference = 'Stop'

if ($ModeOrAction -in @('status', 'stop', 'build', 'build-only')) {
    $Action = $ModeOrAction
    $Mode = 'both'
} elseif ($ModeOrAction -in @('start')) {
    $Mode = 'electron'
    $Action = 'start'
} else {
    $Mode = $ModeOrAction.ToLowerInvariant()
}

$UseWsl = [bool]($WslDistribution -and $WslRepoPath)
$WebStateFile = Join-Path $env:TEMP 'scratchrobin-web.port'
$WebUrl = "http://127.0.0.1:$Port"
if (Test-Path $WebStateFile) {
    $SavedPort = (Get-Content $WebStateFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($SavedPort) { $WebUrl = "http://127.0.0.1:$SavedPort" }
}

if ($UseWsl) {
    # Delegate build/server lifecycle into WSL2 Ubuntu-24.04 and open browser on Windows host
    if ($Action -eq 'open') {
        Start-Process $WebUrl
        exit 0
    }
    $WslArgs = @()
    if ($Mode -in @('electron', 'web')) { $WslArgs += $Mode }
    $WslArgs += $Action
    if ($Mode -eq 'web') { $WslArgs += @('--port', "$Port", '--no-open') }
    & wsl.exe --distribution $WslDistribution --cd $WslRepoPath --exec bash ./start_robin.sh @WslArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Mode -eq 'web' -and $Action -eq 'start' -and -not $NoOpen) {
        Set-Content -Path $WebStateFile -Value "$Port" -Encoding Ascii
        Start-Process "http://127.0.0.1:$Port"
    }
    exit 0
}

# Native Windows x64 path
$PythonExe = Join-Path $NativeRepoPath '.venv\Scripts\python.exe'
$WebScript = Join-Path $NativeRepoPath 'web\CDEadmin.py'
$RuntimeDir = Join-Path $NativeRepoPath 'runtime'
$ElectronExe = Join-Path $RuntimeDir 'node_modules\electron\dist\electron.exe'
$BundleFile = Join-Path $NativeRepoPath 'web\pgadmin\static\js\generated\app.bundle.js'
$NativeEvidence = Join-Path $env:TEMP 'sr-native-stage'

function Get-RobinElectronProcesses {
    Get-CimInstance Win32_Process -Filter "Name = 'electron.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($RuntimeDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 }
}

function Get-RobinWebProcesses {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.IndexOf($WebScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        }
}

function Invoke-BundleBuild {
    $env:SCRATCHROBIN_DDN_SOURCE = $DdnSourcePath
    & $PythonExe (Join-Path $NativeRepoPath 'tools\development\native.py') frontend --evidence $NativeEvidence
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed with exit code $LASTEXITCODE" }
}

switch ($Action) {
    'status' {
        if (Test-Path $BundleFile) {
            Write-Host "Latest bundle    : $BundleFile ($((Get-Item $BundleFile).LastWriteTime))"
        } else {
            Write-Host "Latest bundle    : NOT BUILT"
        }
        if ($Mode -ne 'web') {
            $ep = @(Get-RobinElectronProcesses)
            Write-Host ("Electron desktop : " + $(if ($ep.Count -gt 0) { "RUNNING (PID $($ep[0].ProcessId))" } else { "STOPPED" }))
        }
        if ($Mode -ne 'electron') {
            $wp = @(Get-RobinWebProcesses)
            Write-Host ("Web browser mode : " + $(if ($wp.Count -gt 0) { "RUNNING ($WebUrl, PID $($wp[0].ProcessId))" } else { "STOPPED" }))
        }
    }
    'stop' {
        if ($Mode -ne 'web') {
            foreach ($p in @(Get-RobinElectronProcesses)) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
            Write-Host 'Electron desktop stopped.'
        }
        if ($Mode -ne 'electron') {
            foreach ($p in @(Get-RobinWebProcesses)) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
            Remove-Item $WebStateFile -Force -ErrorAction SilentlyContinue
            Write-Host 'Web server stopped.'
        }
    }
    'start' {
        if (-not (Test-Path $BundleFile)) { Invoke-BundleBuild }
        if ($Mode -eq 'web') {
            Set-Content -Path $WebStateFile -Value "$Port" -Encoding Ascii
            $env:PGADMIN_SERVER_MODE = 'OFF'
            $env:PGADMIN_INT_PORT = "$Port"
            Start-Process -FilePath $PythonExe -ArgumentList @($WebScript) -WorkingDirectory (Join-Path $NativeRepoPath 'web') -WindowStyle Hidden
            $Ready = $false
            for ($i = 0; $i -lt 40; $i++) {
                try {
                    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/browser/" -UseBasicParsing -TimeoutSec 2
                    if ($resp.StatusCode -eq 200) { $Ready = $true; break }
                } catch {}
                Start-Sleep -Milliseconds 500
            }
            if (-not $Ready) { throw "ScratchRobin Web server did not respond on port $Port" }
            Write-Host "ScratchRobin Web ready at http://127.0.0.1:$Port"
            if (-not $NoOpen) { Start-Process "http://127.0.0.1:$Port" }
        } else {
            Start-Process -FilePath $ElectronExe -ArgumentList @('.') -WorkingDirectory $RuntimeDir
            Write-Host 'ScratchRobin Electron desktop launched.'
        }
    }
    'open'       { Start-Process $WebUrl }
    'build-only' { Invoke-BundleBuild }
    'build'      { Invoke-BundleBuild; & $PSCommandPath $Mode start -Port $Port -NoOpen:$NoOpen }
}
```

Companion wrappers in the same folder:
- `start_robin_electron.ps1`: `& "$PSScriptRoot\start_robin.ps1" electron @args`
- `start_robin_web.ps1`: `& "$PSScriptRoot\start_robin.ps1" web @args`

#### B. `_engine_ctl.ps1` and `<engine>.ps1` (`start | stop | status` on Windows WSL2 Estate)

```powershell
# Shared Windows PowerShell controller for WSL2-hosted ScratchRobin test engines.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Engine,
    [Parameter(Mandatory = $true, Position = 1)][ValidateSet('start','stop','status','restart','seed','verify','test')][string]$Action,
    [string]$Distribution = 'Ubuntu-24.04',
    [string]$WslRepoPath = '/home/developer/src/CDEadmin'
)
$ErrorActionPreference = 'Stop'
$Cmd = "source '$WslRepoPath/tools/reference_engine_demos/environment.sh' && '$WslRepoPath/.venv/bin/python' '$WslRepoPath/tools/reference_engine_demos/demo_estate.py'"

switch ($Action) {
    'start'   { & wsl.exe --distribution $Distribution --exec bash -lc "$Cmd start $Engine && $Cmd status $Engine" }
    'stop'    { & wsl.exe --distribution $Distribution --exec bash -lc "$Cmd stop $Engine && $Cmd status $Engine" }
    'status'  { & wsl.exe --distribution $Distribution --exec bash -lc "$Cmd status $Engine" }
    'restart' { & wsl.exe --distribution $Distribution --exec bash -lc "$Cmd stop $Engine && $Cmd start $Engine && $Cmd status $Engine" }
    'seed'    { & wsl.exe --distribution $Distribution --exec bash -lc "$Cmd seed $Engine" }
    'verify'  { & wsl.exe --distribution $Distribution --exec bash -lc "$Cmd verify $Engine" }
    'test'    { & wsl.exe --distribution $Distribution --exec bash -lc "$Cmd start $Engine && $Cmd verify $Engine" }
}
exit $LASTEXITCODE
```

And each `<engine>.ps1` (e.g., `firebird.ps1`, `postgresql.ps1`, `mysql.ps1`, `mariadb.ps1`, etc.) is a one-line wrapper:
```powershell
& "$PSScriptRoot\_engine_ctl.ps1" -Engine 'firebird' @args
```

---

## 7. Final AI Acceptance Checklist Before Reporting Done

Before reporting setup completion to the developer, the AI agent **MUST** verify and report:

1. `doctor` check passed (`bash tools/development/dev.sh doctor` on Linux/WSL2, or `native.py doctor` on Native Windows/macOS) — including verified `Diagram-Design-Notation` sibling checkout.
2. Production frontend bundle (`web/pgadmin/static/js/generated/app.bundle.js`) exists and temporary DDN intake work directories have been cleaned.
3. Requested Docker images are present (`dev.sh images`) and native client tools are bootstrapped (`tools/reference_engine_demos/runtime/connection_profiles.json` rendered on Linux/WSL2, or `.native/` populated on Native Windows/macOS).
4. Requested test/example databases are seeded, verified (`evidence/<engine>.json` records `"status": "passed"`), and registered under the developer's active ScratchRobin user (`cdeadmin@localhost` for Desktop/Single-User Web, or `<email>` for Server Mode).
5. Platform-matched launcher scripts (`start_robin` for **both** Electron and Web Browser + `<engine>` `start|stop|status` scripts + `ENGINE_CREDENTIALS.md`) exist in the developer's workspace directory and `status` succeeds with exit code `0`.
