Dolt native driver contract
===========================

Dolt 1.86.6 uses Connector/Python 26.7.0 transport with native Dolt transaction,
branch, working-set and version-control semantics. SQL COMMIT acknowledges a SQL
transaction; it does not imply DOLT_COMMIT, staging, merge, push or remote
publication. The driver never performs these additional actions automatically.
Existing Dolt-specific catalog and administration forms remain available.

One retained connection has one execution owner until the terminal result is
observed. Native result sets, including CALL results, preserve order and exact
integer, decimal and binary values. Parameters accept named or positional
bindings and encoding/data envelopes. Binary parameters use validated native
hex literals through Connector/Python conversion, preventing arbitrary bytes
from corrupting Dolt expression-column labels. Pages target 256 rows or 1 MiB with two
queued pages; a single large cell may exceed the byte target. Unknown query or
transaction outcomes block connection reuse; no automatic replay occurs.
Optional catalog reads must not roll back pending user work.

Cancellation aborts only the retained connection's socket. It reports an unknown
outcome and requires closing the session, without claiming rollback or undoing
version-control changes. The pure Connector/Python implementation is the default
and provides the qualified cancellation boundary. A connector without that
boundary refuses cancellation. Native KILL remains available through SQL to
users who independently verify their administrative target.

Pool capacity and credential/configuration isolation are preserved, but Dolt
physical connections are discarded on release. A MySQL reset acknowledgement
alone does not establish that all Dolt branch and working-set session state has
been removed. Failed cleanup retains ownership for retry. TLS and authentication
follow the explicit route without security downgrade.

The portable gate creates and drops an owned random database. It qualifies exact
values, ordered pages, metadata with pending changes, SQL commit/rollback,
version-control commits, branch isolation, cancellation, fresh leases and an
optional lost-COMMIT reply. Run ``python tools/cdeadmin_dolt_driver_platform_gate.py
--route ROUTE --evidence OUTSIDE_REPOSITORY``. Supply a server route without a
database or password; credentials are prompted. --no-password is restricted to
an explicitly passwordless owned fixture. --reply-loss requires plaintext
loopback and does not weaken a TLS route. Windows/macOS packaging teams must
retain native platform receipts; Linux qualification does not imply their
acceptance.
