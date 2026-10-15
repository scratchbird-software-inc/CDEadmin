# CDEadmin Linux Build Scripts

CDEadmin is an independent hard fork of pgAdmin 4 9.17. See the repository
`NOTICE` and `LICENSE` files for upstream attribution and licence terms.

Packaging notice (14 October 2026): ScratchRobin now requires Python 3.14 or
newer. DEB/RPM builders must supply and qualify that interpreter and rebuild
native extensions for its ABI. The existing distribution targets and scripts
have not yet passed this new gate; do not infer package readiness from a
successful source installation. See `docs/en_US/python_runtime_policy.rst`.

This directory contains package build scripts and assets that are common to 
various Linux distributions. 

You should not use them directly, but the functionality provided can be used to
simplify your own build scripts (typically by sourcing *build-functions.sh*).
