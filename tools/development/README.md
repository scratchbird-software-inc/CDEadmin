# New-machine development setup: ScratchRobin CDE Administrator

This is the setup guide for a developer with a fresh checkout, not a production
deployment guide. It includes the Python application, built browser UI, native
client tools, and reference-engine Docker samples. Native ScratchBird is excluded.
The scripts reuse the existing engine-specific fixtures rather than creating a
second, incompatible Compose stack.

## 1. Choose where the workspace runs

| Host | Full-estate execution environment | Launcher |
| --- | --- | --- |
| Linux x86_64 | Ubuntu 24.04 x86_64, local Docker Engine | `bash tools/development/dev.sh` |
| Windows x86_64 | Ubuntu 24.04 under WSL2; application and Docker in Linux | `dev.ps1`, or the Linux launcher in WSL |
| macOS Intel | Ubuntu 24.04 x86_64 VM or remote x86_64 Linux machine | `remote.py` over SSH, or Linux launcher inside VM |
| Apple Silicon / Windows ARM / Linux ARM | Remote x86_64 Linux development machine recommended | `remote.py` |

The existing bootstrap extracts Linux `.so` libraries and executable clients.
Native PowerShell/macOS Python cannot load them. An ARM guest with amd64 Docker
images alone does not solve host-client architecture or CPU instruction-set
compatibility. Full amd64 emulation is not qualified by this guide.

These are deployment instructions, not a claim that every engine has passed on
each host. Wrapper unit tests do not substitute for fresh-machine acceptance.
Linux is the current implementation baseline. Run the acceptance checklist below
on each developer's WSL/VM, especially distributed-engine network tests.

Use a local disk inside the Linux guest for the checkout and data. On WSL prefer
`/home/<user>/src/CDEadmin`, not `/mnt/c/...`. Use a remote IDE/SSH or WSL integration
to edit those files. Run Git, Python, Node, Go and Docker commands in that same
Linux environment. Never reuse another machine's `.venv`, `node_modules`,
configuration database, generated client libraries, or rendered profile paths.

Planning allowance: 8 vCPUs, 32 GiB RAM and 100+ GiB free disk is a reasonable
starting point for sequential engine testing, not a measured minimum or a promise
that every engine can run simultaneously. Images, source builds and evidence grow
over time. Start one engine at a time.

## 2. Prepare the host/guest

### Linux and Ubuntu guests

Install Docker Engine and Compose v2 following the
[official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Allow your developer account to use Docker according to local security policy;
Docker access is highly privileged. Do not run the application with sudo.

Install the native build prerequisites in Ubuntu:

```bash
sudo apt update
sudo apt install git ca-certificates curl build-essential pkg-config \
  python3 python3-venv python3-dev libpq-dev libkrb5-dev \
  libmariadb-dev libmariadb-dev-compat libssl-dev libffi-dev \
  libsnappy-dev zlib1g-dev libreadline-dev tcl-dev default-jdk \
  libtommath1 libncurses6
```

Install Node.js 22 LTS with Corepack (the tested line is 22.22.x), and Go **1.25.5
or newer**. Go's minimum comes from the checked-in TiKV helper's `go.mod`, not the
Ubuntu package version. Follow [Node downloads](https://nodejs.org/en/download)
and [Go installation](https://go.dev/doc/install). If Corepack is absent, install
it using your Node installation's supported mechanism. Do not upgrade the Yarn
lockfile: `web/package.json` declares the required package manager version.

Validate tools:

```bash
docker version
docker compose version
node --version
corepack --version
go version
javac -version
```

For OpenSearch, check the Docker daemon host's map-count limit:

```bash
sysctl vm.max_map_count
# If below 262144, and approved for this development host:
sudo sysctl -w vm.max_map_count=262144
```

Persist that setting using your system's sysctl configuration if needed. See
[OpenSearch host settings](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker/).
The setup scripts do not alter kernel settings or disable swap globally.

### Windows

In an Administrator PowerShell terminal:

```powershell
wsl --install -d Ubuntu-24.04
wsl --list --verbose
```

Restart Windows if requested and complete Ubuntu user creation. Use WSL version 2.
See [Microsoft's WSL instructions](https://learn.microsoft.com/en-us/windows/wsl/install).
For the closest full-estate topology to native Linux, install Docker Engine inside
the Ubuntu distribution and use its local Unix socket. Ensure its Docker service
is running. Do not simultaneously enable Docker Desktop integration for that
distribution and run a second Docker Engine there.

Docker Desktop's WSL2 integration is another option for basic fixtures; follow
[Docker's WSL2 instructions](https://docs.docker.com/desktop/features/wsl/).
Do not assume it validates TiKV's advertised peer addresses or every multi-node
topology. If those tests fail across the Desktop VM boundary, use the local
Linux-daemon topology or a remote Linux machine instead of exposing all ports.

Clone and perform steps 3–7 in Ubuntu. Optionally invoke the same stages from
PowerShell using a host-accessible copy of the checked-in launcher:

```powershell
& '\wsl.localhost\Ubuntu-24.04\home\alice\src\CDEadmin\tools\development\dev.ps1' `
  -Repository /home/alice/src/CDEadmin doctor
```

Replace the Linux username/path. The wrapper does not install WSL or Docker and
does not change execution policy. If policy blocks the script, run the Linux
commands in Ubuntu rather than disabling organization security policy.

### macOS and remote Linux

Create an Ubuntu 24.04 **x86_64** VM on an Intel Mac, or provision an x86_64 Linux
development machine. For Apple Silicon use a remote x86_64 machine unless you are
explicitly qualifying full-system emulation. Install SSH on the guest and use
key-based authentication. Clone into the guest and perform the Linux setup there.

From a host checkout with Python 3 installed:

```bash
python3 tools/development/remote.py developer@vm-host /home/developer/src/CDEadmin doctor
python3 tools/development/remote.py developer@vm-host /home/developer/src/CDEadmin run
```

In a second host terminal, forward only the application port:

```bash
ssh -N -L 127.0.0.1:5051:127.0.0.1:5051 developer@vm-host
```

Then browse to `http://127.0.0.1:5051`. Database connections originate in the Linux
guest, so profiles remain `127.0.0.1` **inside the guest**, not the Mac's IP address.
Do not point the host checkout at a remote Docker daemon: bootstrap bind mounts
and extracted native libraries belong on the Docker host. The SSH launcher runs
the whole workflow there instead.

## 3. Clone and check prerequisites

In the Linux execution environment:

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/DaltonCalford/CDEadmin.git
cd CDEadmin
git rev-parse HEAD
bash tools/development/dev.sh doctor
```

Use the team's release/branch/commit if different. Record the commit for QA.
`doctor` checks tools, versions, CPU/OS and Docker access without installing
anything. A pass is not a dependency ABI check or an engine qualification result.

## 4. Install application dependencies and build

```bash
bash tools/development/dev.sh python
bash tools/development/dev.sh frontend
bash tools/development/dev.sh clients
```

- `python` creates a repository-local `.venv`, installs the application and demo
  requirements together, and runs `pip check`. It does not use `pip --user` or
  modify global Python packages. Dependency conflicts are failures, not ignored.
- `frontend` uses `corepack yarn install --immutable`, compiles the theme, and
  builds production assets. Peer warnings must be assessed separately from a
  successful build. Do not use a blind Yarn upgrade or `npm audit fix --force`.
- `clients` downloads/builds pinned native tools, checks the SQLite source hash,
  extracts matching Docker-image clients, builds fixture helpers, and renders
  `tools/reference_engine_demos/runtime/connection_profiles.json` with this
  checkout's absolute paths. This requires network access and substantial disk.

The demo requirements deliberately pin `firebird-driver==1.10.11`; do not
independently upgrade to 2.x in this shared environment without resolving its
protobuf requirements against the cloud/vector clients. The combined install is
the authoritative check. The native Firebird client is separately versioned.

For logs, use Bash pipefail and tee, for example:

```bash
mkdir -p .devstate/logs
set -o pipefail
bash tools/development/dev.sh clients 2>&1 | tee .devstate/logs/clients.log
```

Do not pipe interactive account setup through a logger or place login passwords
on command lines. Do not commit logs containing private connection information.

## 5. Configure and create the developer account

```bash
bash tools/development/dev.sh configure
bash tools/development/dev.sh init
```

`configure` exclusively creates `web/config_local.py` from the checked-in example.
It **refuses to overwrite an existing file**. Review an existing configuration
manually, particularly absolute paths, port, server mode and debug mode.
The example places application data under `.devstate/application`, binds HTTP to
loopback port 5051, enables login and encrypted password saving, and disables
debug mode. It requires no `/var/lib` or `/var/log` permissions.

`init` runs `web/setup.py setup-db` and prompts for the initial application email
and password. These are **not** database demo credentials. Use a personal test
account and a unique password. On first engine connection follow the application's
master-password flow before saving credentials. Do not copy another developer's
configuration SQLite database, cookies or encrypted password store.

## 6. Create, verify and register samples

Begin with PostgreSQL:

```bash
bash tools/development/dev.sh start postgresql
bash tools/development/dev.sh seed postgresql
bash tools/development/dev.sh verify postgresql
bash tools/development/dev.sh register --user developer@example.com --dry-run
bash tools/development/dev.sh register --user developer@example.com
bash tools/development/dev.sh run
```

Use the email created in step 5. Registration backs up the config database, adds
the profiles/database targets and enables connector roots. It does not start all
engines, prove connectivity, or silently save their passwords. Register before
starting the web process, or close it first. Rerunning registration may restore
fixture settings; back up local customizations beforehand.

Browse to `http://127.0.0.1:5051`, log in, and expand PostgreSQL → localhost →
`cdeadmin_demo`. For this fixture: host `127.0.0.1`, port **55432**, username and
database **cdeadmin_demo**, password **CDEadminDemo-2026!**.

For all reference samples, run sequential preparation when sufficient resources
and download time are available:

```bash
bash tools/development/dev.sh prepare all
```

This seeds/verifies each logical profile, collects failures, and stops network
fixtures between checks. It does **not** leave every server running. Seeding can
recreate fixture objects or overwrite sample rows: use only disposable demos,
never point these commands at production or valuable custom data.

## 7. Daily per-engine lifecycle

```bash
bash tools/development/dev.sh list
bash tools/development/dev.sh start firebird
bash tools/development/dev.sh seed firebird
bash tools/development/dev.sh verify firebird
bash tools/development/dev.sh status firebird
bash tools/development/dev.sh stop firebird
# Stop all project demo services; does not delete volumes:
bash tools/development/dev.sh stop all
```

Substitute any ID returned by `list`. This includes all 26 logical profiles for
the 25 reference entries (YugabyteDB has YSQL and YCQL). OpenSearch SQL/PPL shares
the OpenSearch deployment; YugabyteDB YSQL/YCQL share another. Stopping either
shared interface stops that deployment. SQLite and DuckDB are embedded files,
not Docker servers. Closing CDEadmin does not stop Docker demos.

Existing individual launchers also remain available, e.g.
`bash tools/reference_engine_demos/lifecycle/postgresql.sh start` after activating
`.venv`. `test` in those launchers means start+verify, **not seed**.

For engine-specific ports, usernames, passwords, paths, secondary endpoints and
tool settings see the checked-in
[profile template](../reference_engine_demos/connection_profiles.template.json)
and the generated `runtime/connection_profiles.json`. The rendered file is the
local source of truth. Firebird's database path is a path **inside its container**;
SQLite/DuckDB paths are files **in this checkout**. Profiles without a password
use their explicitly configured demo authentication mode; do not invent one.
Images and exact versions are recorded in
[engine_versions.json](../reference_engine_demos/engine_versions.json).

## Isolation, networking and persistence

- Demo credentials are public test credentials. Several engines intentionally
  disable authentication/TLS for local fixtures. Do not expose them to a LAN.
- Ports normally bind to loopback. TiKV is an exception: its advertised peer
  address must be reachable both from containers and the Linux host. Inspect the
  generated topology and restrict host/network access before starting it.
- The checkout, Docker daemon and native Python clients must share the documented
  Linux execution environment. A container's localhost is not the host's.
- Cassandra uses additional loopback addresses `127.0.0.2` and `127.0.0.3`. Do not
  collapse these to one endpoint when diagnosing discovery.
- The fixtures use fixed names and ports: one demo estate per Docker daemon.
  Separate checkouts on one daemon are not independent estates.
- Named Docker volumes survive stop/start; embedded files are under
  `tools/reference_engine_demos/data/`. Bootstrap assets/profiles are in
  `runtime/`; verification artifacts are in the sibling `evidence/` directory.
- `.venv`, `.devstate`, config overrides and demo generated state are ignored by
  Git. Do not run `docker system prune --volumes` as a troubleshooting shortcut.
- Scripts may replace obsolete *demo container definitions*, retaining their
  volumes. Read the engine README before applying them to an existing estate.

## Troubleshooting and acceptance

| Symptom | Check/action |
| --- | --- |
| Docker unavailable | Start the daemon, check `docker context show`, permissions and WSL integration. Do not run the app as root. |
| Port occupied | Inspect `docker ps` and `ss -ltn`; stop the conflicting owned demo. Changing a port requires coordinated fixture/profile changes. |
| `mariadb_config` or `pg_config` missing | Install the corresponding development packages before the Python stage. |
| Python dependency conflict | Use the project `.venv` and combined requirements. Preserve pip output; do not silently downgrade global packages. |
| Native library cannot load | Use x86_64 Linux, run clients stage, use `dev.sh run`; inspect `ldd` for missing libraries on the named failing binary. |
| Server running but no sample | Run `seed ENGINE`, then `verify ENGINE`; starting alone does not populate it. |
| Wrong password with an old volume | Initialization environment variables do not reset an existing database user's password. Preserve data and inspect that fixture; do not delete the volume blindly. |
| TiKV/cluster discovery fails in a VM | Check advertised addresses, guest routing, Docker bridges and firewall. Passing a TCP check on one port is insufficient. |
| UI not updated | Rerun frontend stage, restart the Python process, hard reload, reopen existing forms. |
| `/var/log` permission error | Review `web/config_local.py`; use the template's user-owned paths. |
| Save password unavailable | Check master-password/session policy and connection state. Do not disable encryption to work around it. |

Before calling a new workstation ready, record: commit, OS/architecture, tool
versions, `pip check`, build result, per-engine verification results, and browser
login/connector/database/query checks. Where supported, test an edit with rollback
and a separate committed edit against disposable sample rows. An engine-native
verification pass does not certify every UI form or every provider feature.

This guide does not perform a fresh install on Windows/macOS on your behalf.
Those host paths and every requested engine must be verified on the target
machine. Missing prerequisites or failed engines are blockers, not passes.
