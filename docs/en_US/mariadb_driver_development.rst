MariaDB driver development and platform handoff
===============================================

Scope and native dependencies
-----------------------------

ScratchRobin uses MariaDB Connector/Python 1.1.14 with MariaDB Connector/C and
qualifies against MariaDB 12.2.2. MariaDB retains its own connector, TLS and
authentication options, native types, catalogs, administrative forms and command
line tools. MySQL-only options are not exposed as MariaDB options.

The native connector requires two fidelity corrections: preservation of zero
and partial temporal values, and propagation of errors in later result sets.
A stock ``mariadb==1.1.14`` installation is insufficient. The reproducible build
below applies the narrowly scoped patch retained in ``tools/driver_patches/``.
The version string remains 1.1.14; the build receipt's source, patch and wheel
hashes identify the actual build. Query cursors check for the opt-in extension.
Catalog cursors keep normal Python conversion. Keep the matching Connector/C
runtime available to the application; do not interchange its ABI arbitrarily.

The Linux native receipt uses Python 3.12.3. Use the project's supported Python
version and qualify a different Python/ABI combination with its own receipt.
Windows developers need the project's supported Python and Node toolchains,
Git, Python development headers, Visual Studio C++ Build Tools and the matching
architecture of MariaDB Connector/C development/runtime files. Configure
``MARIADB_CC_INSTALL_DIR`` according to the connector's bundled build
configuration. macOS developers need Xcode command-line tools and a matching
MariaDB Connector/C installation exposing ``mariadb_config`` on PATH. Linux
uses its compiler, Python development package and Connector/C development
package. The upstream source's build configuration remains authoritative for
platform library discovery. Use a project virtual environment and install
``pip``, ``setuptools``, ``wheel`` and ``packaging`` there.

Building the native extension
-----------------------------

Download the official MariaDB 1.1.14 source distribution from PyPI into the
external project work area. Its SHA-256 must be
``e6d702a53eccf20922e47f2f45cfb5c7a0c2c6c0a46e4ee2d8a80d0ff4a52f34``.
The build tool rejects different archives, applies the exact patch with Git,
builds outside the repository and retains source, logs and a wheel receipt::

   python -m tools.cdeadmin_build_mariadb_driver --archive <mariadb-1.1.14.tar.gz> --output <new-external-build-directory>
   python -m pip install --no-deps --force-reinstall <resulting-wheel>

Do not subsequently replace that wheel with the stock same-version package.
Distribute the corresponding patched source and upstream license notices with
any redistributed binary as required by the connector license. The patch and
its provenance are described in ``tools/driver_patches/README.rst``. Wheel
construction alone does not qualify a platform.

Native qualification
--------------------

Use a disposable MariaDB 12.2.2 server and an account authorized to create and
remove uniquely named test databases, routines and tables and cancel its own
queries. Set PYTHONPATH to the repository's ``web`` directory. Create a route
JSON containing native host/port/user/TLS options, without credentials or an
existing database. Invoke::

   python -m tools.cdeadmin_mariadb_driver_platform_gate --route <route.json> --evidence <new-external-evidence-directory>

The tool prompts for the password without logging it; ``--no-password`` is only
for an explicitly passwordless fixture. It creates and removes its own schemas
and records platform, Python, connector versions, TLS observation, source hashes,
checks and failures. It does not weaken supplied TLS options to inject faults.
Run on Windows and macOS with the actual packaged application environment.
Receiving teams own their native receipts and UX/QA acceptance; defects in these
low-level drivers return to this workstream. Linux receipts do not prove those
platforms or enterprise authentication deployments.

The owned-container gates independently cover private pools and credential
rotation, exact temporal/numeric/binary values in both protocols, ordered native
result sets, bounded pages, later-result errors, cancellation, lost COMMIT replies,
TLS 1.2/1.3 and certificate rejection, compression, host-list failover and native
LOCAL import enable/disable. Their entry points are the MariaDB driver,
connection_ownership, execution, tls, connection_modes and local_infile tools in
``tools/``. Each accepts an external evidence directory and removes its own
container. Docker and OpenSSL are needed for those owned-container fixtures,
not for the portable platform gate.

Behavior surfaced for UX
------------------------

Query forms accept named objects and positional parameter arrays. Use typed
``integer``, ``decimal`` or ``base64`` envelopes for values that cannot be safely
represented in browser JSON. Integer envelopes outside native signed/unsigned
64-bit range bind as exact DECIMAL to prevent binary-protocol truncation.
Unsafe-size integers and decimal results remain
strings; binary results retain base64 data and byte length. Native column
metadata and duplicate labels are retained under distinct column identities.
Temporal results remain exact native text, including zero dates and extended
negative TIME. Connector/Python's connection character set is UTF8MB4; the
provider does not offer a fictitious alternate-charset connection setting.

The workspace polls bounded result pages, identifies each result set and offset,
and preserves displayed pages when a later error arrives. One oversized row
can exceed a page's byte budget; this is not a chunked BLOB interface. Transaction
controls cannot race an active worker. A lost finality response yields unknown
state, blocks reuse and never replays the operation, even if another session
can independently observe committed work. Close the unknown session and perform
explicit reconciliation before deciding on a new operation.

Pool names are provider-local. Changed credentials or connection defaults retire
the old generation while leased connections finish on their original attachment.
Rollback/reset failures discard the connection. Native reset is followed by
restoration of the configured database/autocommit and initial command. Automatic
reconnect is rejected; failover applies before session establishment only.

MariaDB native LOCAL import supports its own Boolean switch; MySQL's optional
path-restricted import setting is not advertised for this connector. Native
administrative executables remain separately installed MariaDB tools and keep
their existing grants/workspace restrictions. These driver receipts do not claim
blanket console, management workflow or platform UX acceptance.
