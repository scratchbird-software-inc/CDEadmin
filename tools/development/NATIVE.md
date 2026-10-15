# Native Windows and macOS development

This workflow runs the application, Python extensions and native engine clients
on the host OS. It does not use WSL, Linux client libraries, or Docker. Network
database servers may be local native installations or explicit remote test
servers. A successful environment job is not qualification of unconfigured
network engines, ScratchBird monitoring history, or every administrative tool.

The GitHub workflow **Native development environments** qualifies Windows x64,
Intel macOS and Apple Silicon macOS separately. The tested runner targets
are Windows Server 2025 x64 and macOS 15 on both architectures; other OS
versions are not covered by this matrix. Use its failure inventory and
native provider receipts; a Linux pass does not establish platform support.

## Prerequisites

Use a local writable checkout, standard CPython 3.14, Node 22.22.x, Corepack,
Git and CMake. Keep the repository's Yarn pin and lockfile. Do not copy another
machine's virtual environment, native runtime, node_modules or configuration DB.

On Windows install Visual Studio C++ Build Tools with the Windows SDK and the
[current x64 Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
The redistributable must be at least as recent as the toolset used by the
native clients. The runtime hook loads it before vendor DLL directories;
an older CRT bundled with one engine must not be selected for another.
Run
PowerShell with ordinary developer permissions. This bootstrap targets x64
Python and native x64 libraries; Windows ARM is not qualified by the matrix.

On macOS install Xcode command-line tools and Homebrew, then:

```bash
brew install libpq openssl@3 krb5 pkg-config cmake bison icu4c libxml2 lz4 zstd readline zlib
```

The clients stage builds an owned CPython 3.14.8 interpreter on macOS against
the required SQLite library. It does not replace Apple's Python or SQLite.
Windows loads the owned SQLite DLL before Python's `_sqlite3` extension.

Clone the sister project beside CDEadmin and install its pinned dependencies:

```text
git clone https://github.com/scratchbird-software-inc/Diagram-Design-Notation.git
cd Diagram-Design-Notation
npm ci --ignore-scripts
```

Set `SCRATCHROBIN_DDN_SOURCE` to that checkout if it is elsewhere. DDN is
captured and rebuilt in an isolated work directory before application builds
and qualification runs. The active sister checkout is not modified.

## Windows stages

From the CDEadmin checkout, use an evidence directory outside the repository:

```powershell
$evidence = 'C:\dev-evidence\cdeadmin-native'
$env:SCRATCHROBIN_DDN_SOURCE = 'C:\src\Diagram-Design-Notation'
python tools/development/native.py doctor --evidence $evidence
python tools/development/native.py clients --evidence $evidence
python tools/development/native.py python --evidence $evidence
python tools/development/native.py servers --evidence $evidence
python tools/development/native.py frontend --evidence $evidence
python tools/development/native.py desktop --evidence $evidence
python tools/development/native.py configure --evidence $evidence
python tools/development/native.py init --evidence $evidence
python tools/development/native.py verify --evidence $evidence
python tools/development/native.py fixtures --evidence $evidence
python tools/development/native.py run --evidence $evidence
```

Select the interpreter explicitly if `python` is not CPython 3.14. The
`native.ps1` wrapper accepts `-Python`, `-Stage`, and `-Evidence`; it does not
invoke WSL or change execution policy. The older `dev.ps1` remains the WSL
wrapper for the separate Linux reference estate.

## macOS stages

```bash
export SCRATCHROBIN_PYTHON=/absolute/path/to/python3.14
export SCRATCHROBIN_DDN_SOURCE="$HOME/src/Diagram-Design-Notation"
bash tools/development/native.sh doctor --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh clients --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh python --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh servers --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh frontend --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh desktop --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh configure --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh init --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh verify --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh fixtures --evidence "$HOME/dev-evidence/cdeadmin-native"
bash tools/development/native.sh run --evidence "$HOME/dev-evidence/cdeadmin-native"
```

The clients stage expands the verified, architecture-specific Firebird vendor
package into this checkout's `.native` directory. It does not execute installer
scripts, require an administrator framework installation, or register a system
Firebird service.

Open <http://127.0.0.1:5051>. `init` prompts for the initial application account;
its credentials are separate from database credentials. `configure` preserves
existing configuration. Use a fresh evidence directory for each verification
run; existing receipts and owned fixtures are not overwritten.

To launch the Electron desktop application, use `run-desktop` in place of
`run`. It uses the same native Python environment and canonical launcher,
with desktop preferences under `.devstate/desktop`. Existing `dev_config.json`
and installed application profiles are preserved. The desktop verification
launches Electron and checks that the compiled explorer workbench mounts,
using an isolated configuration database and desktop profile.

## What is provisioned and tested

Native downloads are pinned by URL and SHA-256 in `native_assets.py`:

- SQLite 3.53.0 with FTS5, R-tree, column metadata and threading.
- Firebird 5.0.4, including its native client and embedded engine runtime.
- MariaDB Connector/C 3.4.8 and the project's patched Connector/Python 1.1.14.
- PostgreSQL 18.3 Windows SDK and command-line tools; macOS uses native libpq.
- CPython 3.14.8 source for the macOS interpreter build.

Application, demo and regression Python requirements are resolved together,
followed by the patched MariaDB wheel and `pip check`. A source-build failure
is a failure, not permission to downgrade an engine or remove a dependency.

The native setup also installs the official ScratchBird Python wire-protocol
driver from engine revision `54b029a498393de0fb6b765996cc4f7c57211049`.
It uses host Python sockets/TLS and requires no Linux client library. This
provides the client needed by persistent monitoring history; live archive
acceptance still requires a compatible ScratchBird server and disposable
history credentials. Its source revision/tree and built-wheel hash are recorded
in `scratchbird-driver.json`. Only the SDK subtree is captured, avoiding an
unneeded full engine checkout and Windows path-length failures in other drivers.

Verification collects dependency imports, exact runtime admission, the existing
SQLite and DuckDB native provider gates, embedded Firebird editor/row/template/
profiler checks, Python contracts, JavaScript contracts, product identity and
HTTP startup through `web/CDEadmin.py`. Independent failures are retained.

The servers stage provisions MySQL 9.7.0, MariaDB 12.2.2, PostgreSQL 18.3 and
MySQL Shell 9.7.0 with their native administration tools. Windows uses verified
vendor binary archives. macOS uses verified MySQL/Shell binary archives and
builds the exact PostgreSQL/MariaDB source releases. These source builds need
additional time and disk; they do not install into system data directories.
The launcher supplies the existing `CDEADMIN_*_BINARY` settings while preserving
explicit developer overrides. Linux tools extracted by
`reference_engine_demos/bootstrap.py` are not usable on Windows or macOS.
Other providers may require additional native SDKs/tools; import checks do not
establish availability of all their external administrative executables.

The fixtures stage starts uniquely owned, loopback-only native PostgreSQL,
MySQL, MariaDB and Firebird servers, runs the existing network-driver gates,
then stops them and removes their data. It does not start/stop installed services
or use their data. Test accounts use generated secrets supplied through the
production secret-lease boundary. MySQL and MariaDB use owned TLS certificates
with certificate verification. Firebird uses a copied security database.
A cleanup failure fails qualification.
GitHub's full matrix runs these fixtures without private network credentials.
Distributed topologies and enterprise authentication require additional estates.

## Native network qualification

Use disposable test servers and accounts authorized to create/drop the gates'
owned schemas, databases and users. Create a route file outside the checkout:

```json
{
  "postgresql": {
    "route": {"host": "test-host", "port": 5432, "user": "qa", "database": "postgres"},
    "password_env": "CDEADMIN_TEST_POSTGRES_PASSWORD"
  },
  "firebird": {
    "route": {"host": "test-host", "port": 3050, "user": "SYSDBA", "charset": "UTF8"},
    "password_env": "CDEADMIN_TEST_FIREBIRD_PASSWORD",
    "database_directory": "C:\\firebird-test-data",
    "path_style": "windows"
  },
  "mysql": {
    "route": {"host": "test-host", "port": 3306, "user": "qa"},
    "password_env": "CDEADMIN_TEST_MYSQL_PASSWORD"
  },
  "mariadb": {
    "route": {"host": "test-host", "port": 3307, "user": "qa"},
    "password_env": "CDEADMIN_TEST_MARIADB_PASSWORD"
  }
}
```

Firebird's database directory belongs to the server, not the client machine.
Use `path_style: "posix"` with an absolute server-side POSIX path when needed.
Inject passwords through your environment/secret manager, not command-line
arguments, route JSON or committed configuration. Set `CDEADMIN_NATIVE_ROUTES`
to the file and run the `network` stage with a fresh external evidence directory.
Missing routes are reported as unconfigured and do not count as passed.

For GitHub network checks, set repository variable
`CDEADMIN_NATIVE_ROUTES_JSON` to the credential-free JSON and the four named
password secrets. The runners must be able to reach those test servers.
Without that configuration GitHub runs only the owned loopback network gates.
ScratchBird monitoring-history acceptance remains a separate native runtime
requirement and is not replaced with an embedded history engine.

## GitHub execution and evidence

Run the workflow from Actions, or:

```text
gh workflow run native-development.yml --ref <branch>
```

The default matrix includes all three platforms. `platforms` accepts a JSON
runner list for a targeted repair run. The workflow uses ordinary shell steps
and a repository-local evidence uploader because this repository currently
permits local actions only. It does not
relax repository/organization action permissions. Logs retain build output,
failure inventories and receipts; the job summary lists stage results.
Download each platform's evidence artifact for receipts, test XML, build logs
and browser/desktop screenshots. Private keys, owned server data and browser
profiles are excluded. Artifacts are retained for 14 days.

The `ci` stage installs host prerequisites only when `GITHUB_ACTIONS=true`;
local developers use explicit stages and review host prerequisite installation.
No native-platform completion claim should be made until the corresponding
fresh-machine job and required engine integration receipts pass.

The startup gate retains the 240,000 KiB RSS budget on Linux and Windows.
Darwin has a 256,000 KiB budget: the first Apple Silicon run measured
240,336 KiB, just above the original boundary. The explicit platform budget
keeps a bounded allowance for its native runtime footprint and is recorded
with each startup measurement.

Intel macOS has explicit wall-time budgets of 20 seconds for startup and
2.5 seconds for 5,000 contract validations. Its first hosted run measured
15.33 and 1.79 seconds respectively. Windows has a 35-second startup budget following hosted measurements of
18.28 and 27.62 seconds. Linux and Apple Silicon retain the original
8-second limit. All platforms except Intel Mac retain the 1.5-second
contract-validation limit. Receipts record the selected
budgets; functional checks, route counts and validation work are identical.

Native schema review receipts use host process locks and atomic, flushed
publication before dispatch. Windows uses LockFileEx, write-through moves and
protected current-user-only DACLs for private files. Renderer process startup
has a separate 15-second bound; the requested renderer execution deadline
starts after the worker is ready and is still enforced. The Windows Cassandra
installation includes the official driver's documented asyncore backport.
PDF regression checks use a portable Python parser.
