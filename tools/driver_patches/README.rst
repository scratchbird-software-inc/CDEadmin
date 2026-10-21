MariaDB Connector/Python exact temporal extension
================================================

The patch targets the official ``mariadb-1.1.14.tar.gz`` source distribution
from PyPI, SHA-256
``e6d702a53eccf20922e47f2f45cfb5c7a0c2c6c0a46e4ee2d8a80d0ff4a52f34``.
It modifies the native cursor layout and must be compiled together with the
whole extension. Never substitute the modified header into a stock binary.

The affected upstream files are copyright MariaDB Corporation AB and Georg
Richter, licensed under GNU Library General Public License version 2 or later.
The patch is distributed under those same terms. Preserve upstream license
notices and corresponding patched source with any redistributed binary.
The source archive and the deterministic patch constitute the corresponding
source inputs; the build tool retains the fully patched source alongside its
wheel and receipt. This repository does not publish built wheels.

``cdeadmin_exact_temporals`` defaults to false. Opted-in cursors return native
temporal strings, bypassing the lossy Python-calendar conversion and user
converter callbacks for temporal fields only. SQL NULL remains None. The
binary-protocol decoder formats native fields with their advertised fractional
precision. All other cursors and types retain upstream behavior.

Run ``python -m tools.cdeadmin_build_mariadb_driver --archive <sdist>
--output <external-new-directory>`` with the platform's matching Python headers,
C compiler, MariaDB Connector/C development package, setuptools, packaging,
wheel and Git available. Install the resulting wheel in the application virtual
environment. Do not install it into another team's environment. An unmodified
``mariadb==1.1.14`` package does not satisfy the query-fidelity contract even
though its version string matches. Runtime qualification is a separate step.

The patch also repairs ``nextset()`` error propagation: a positive native
next-result return raises the native server/statement error; only a negative
return denotes exhaustion. This correction applies to all cursors.


MySQL Connector/Python native query attributes
=============================================

Linux development setup and ``bootstrap.py --install-python`` now install this
correction through ``python -m tools.cdeadmin_install_mysql_driver --receipt
<current-receipt.json>``. The installer builds in a disposable external directory,
checks the resulting native ABI/client version and keeps a current receipt. Use
``--mysql-capi`` or ``SCRATCHROBIN_MYSQL_CAPI`` for an existing matching SDK;
otherwise Linux x86_64/glibc2.39+ can extract the three pinned official Ubuntu24.04
SDK packages without installing OS packages. Native Windows/macOS setup retains
its separate platform SDK acquisition. Local installation is separate from
engine functionality qualification and from binary redistribution; preserve
corresponding source and notices when distributing a built binary.

``mysql-connector-python-26.7.0-query-attributes.patch`` targets the official
``mysql_connector_python-26.7.0.tar.gz`` source distribution, SHA-256
``d8ff5ee236ea46661ee639336323e124ed868e37f3ea991bdc5de5a146f39fd5``.
The affected upstream files are copyright Oracle and/or its affiliates and
licensed under GNU GPL version 2 with the upstream OpenSSL and Universal FOSS
exceptions. The patch uses those same terms. Preserve the upstream notices and
corresponding patched source and native SDK source with redistributed binaries.
The build runner retains its patched source, wheel and input fingerprints.

Build with ``python -m tools.cdeadmin_build_mysql_driver --archive <sdist>
--mysql-capi <MySQL-9.7.0-native-SDK-root> --output <external-new-directory>``.
Use the matching platform compiler and Python development headers; setuptools,
wheel, packaging and Git are build prerequisites. Install the resulting wheel in
the application's own virtual environment. The native Windows/macOS setup
provisions its pinned native SDK kit and performs this build and verification;
platform runtime acceptance remains separate. No Linux client is used there.

The complete extension must be rebuilt together with its changed internal
binding structure. Never replace a header in a stock binary. The native marker
``CDEADMIN_QUERY_ATTRIBUTES_ABI == 1`` identifies the correction, not runtime
qualification. The Python package version remains 26.7.0. The patch preserves
native C execution and implements signed/unsigned64, double precision, exact
Decimal, NULL, datetime/time and normalized signed timedelta bindings. It honors
name encoders supplied by text subclasses so ScratchRobin can preserve the
current native source charset. Plain text names retain upstream UTF-8 behavior.
It also fixes Decimal's indexed binding write and cleans up bindings and owned
values on non-result acknowledgements and native errors as well as result rows.
