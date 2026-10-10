MySQL driver development and platform handoff
============================================

ScratchRobin targets MySQL 9.7.0 with ``mysql-connector-python==26.7.0``.
The backend team owns native driver correctness, backend operations and
functional forms. Windows and macOS teams own native UX refinement and platform
QA; driver defects discovered there return to this workstream. MariaDB has a
separate provider and is not substituted for MySQL.

Installation and driver selection
--------------------------------

Install the application requirements, regression requirements and
``tools/reference_engine_demos/requirements.txt`` into a platform-native Python
virtual environment. Python 3.12 is the current Linux qualification baseline.
Keep the pinned connector version. Do not copy a Linux environment or native
extension to Windows/macOS. The pure Python connector does not require a
separate ``libmysqlclient`` installation. Optional authentication mechanisms
retain their connector-specific dependencies and server configuration.

The MySQL connection form defaults ``use_pure`` to true. Disabling it explicitly
requires the connector's C extension for the Python version, architecture and
OS in use; an absent extension is an error. Routes saved without this field
retain Connector/Python's selection behavior. Qualify each implementation you
intend to deploy. The qualified Linux baseline currently uses pure Python;
C-extension and native Windows/macOS receipts must come from those environments.

TLS CA, client certificate/key, certificate verification, hostname verification,
TLS versions and cipher settings are native connector options. They refer to
files readable by the backend process, not the browser machine. Failed
verification is not retried with weaker settings. A control connection used for
query cancellation keeps the authentication and TLS requirements and verifies
the original server UUID before issuing KILL QUERY. Server permissions apply.
MySQL 9.7 excludes the removed ``mysql_native_password`` method from its form
and capability declaration; older routes explicitly choosing it are rejected.

Native behavior
---------------

Provider-private pools isolate endpoints and credential/configuration
generations. Merely selecting reset-on-return does not enable a pool. Pending
work is rolled back before an admitted return; a failed reset discards the
physical connection. No active operation reconnects or replays SQL implicitly.

Queries accept named objects or positional arrays. Exact integer/decimal and
binary envelopes are documented in the query form. Results preserve unsigned
64-bit integers, exact decimals, zero dates, signed extended TIME, JSON text,
Unicode, BLOB, geometry and VECTOR bytes. Duplicate labels receive unique
lookup names while retaining native labels. Catalog reads use their native
metadata path, separately from raw query decoding.
When ``character_set_results=NULL`` is used, each column's charset owns value
decoding. A charset with no matching Python codec is represented as exact
base64 bytes with native charset/collation identity, rather than guessed text.
For a text presentation across storage charsets, retain the default UTF-8
results or explicitly request MySQL's native conversion to UTF-8. Changing SQL
charset variables does not reconfigure the connector's command encoder; edit
the connection character set and open a new session for that purpose.

Execution runs asynchronously. Polling delivers every native result set,
including procedure and affected-row responses, in bounded pages. A page has
its own set index, row offset and end-of-set marker. Later failures do not erase
earlier pages or implicitly roll back earlier work. Queue bounds are two pages,
256 rows and a one-MiB target per page; a larger single row remains intact and
is materialized by the connector. This is not a streaming BLOB API. Query result
history shows recent pages, not an assertion that the last grid is the whole
batch or a whole-result export.

Cancellation requests KILL QUERY through a separate verified connection. The
worker consumes native responses before the session can be reused. Cancellation
does not undo previously executed statements or prove transaction finality.
Failed COMMIT/ROLLBACK replies and unusable connections quarantine the retained
session as unknown, including when the server actually committed. Closing an
unknown session does not claim successful rollback. Do not retry user mutations
to resolve an unknown outcome.

LOAD DATA LOCAL INFILE is disabled by default. Its MySQL-only controls can
admit a directory through ``allow_local_infile_in_path`` while keeping
unrestricted loading disabled. These are client-side paths and native connector
checks. Server ``local_infile`` policy must also permit loading. Imports retain
native transaction behavior; the provider does not commit on the user's behalf.

Portable qualification
----------------------

Use a dedicated MySQL 9.7.0 test server and test principal with permission to
create and drop disposable schemas/tables/procedures and cancel its own queries.
The runner creates random owned schemas and removes them. It does not install a
server, invoke Docker, alter accounts or global configuration, or touch an
existing database. Do not supply a database or password in the route file::

    {
      "host": "mysql-test.example",
      "port": 3306,
      "user": "scratchrobin_test",
      "use_pure": true,
      "ssl_ca": "/absolute/path/to/test-ca.pem",
      "ssl_verify_cert": true,
      "ssl_verify_identity": true,
      "connection_timeout": 10
    }

Use native Windows paths in Windows route JSON, with JSON backslash escaping.
On macOS/Linux, from the repository root::

    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_driver_platform_gate \
      --route /path/to/route.json --evidence /path/to/new-evidence-directory

On Windows PowerShell, from the repository root::

    $env:PYTHONPATH = "web"
    python -B -m tools.cdeadmin_mysql_driver_platform_gate `
      --route C:\test\route.json --evidence C:\test\new-evidence-directory

The password is prompted without echo and supplied through the provider secret
lease. Use ``--no-password`` only for an explicitly passwordless test account.
The evidence destination must be new. Receipts include platform, architecture,
Python/connector/server versions, actual connection class, TLS version, source
hashes, completed scopes and redacted failures. A failure must not be called a
pass. Retain failure artifacts and send driver defects back to the backend team.
Repeat with ``use_pure: false`` when qualifying an installed C extension.

The platform gate exercises exact values, transaction visibility, killed
sessions, multiple native results, later-statement errors, paging and native
cancellation. It does not weaken a supplied TLS route to inject plaintext
faults. Separate uniquely owned Docker fixtures provide reproducible pool,
TLS rejection, local-file policy and lost-COMMIT-reply checks::

    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_connection_ownership_gate --evidence /new/pool-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_execution_gate --evidence /new/execution-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_tls_gate --evidence /new/tls-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_local_infile_gate --evidence /new/import-proof
    PYTHONPATH=web python3 -B -m tools.cdeadmin_mysql_connection_modes_gate --evidence /new/connection-modes-proof

The TLS fixture additionally requires OpenSSL. Those fixture runners use
loopback ephemeral ports and remove only their own containers and volumes.
No Windows/macOS execution, receiving-team acceptance, enterprise identity
provider deployment, or complete management-console UX acceptance is inferred
from Linux driver receipts.
