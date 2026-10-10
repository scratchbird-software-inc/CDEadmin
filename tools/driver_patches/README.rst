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
