FoundationDB native driver contract
==================================

FoundationDB 7.3.77 uses the official API 730 Python/C binding. Each query
session owns its transaction independently, even when the SDK caches a database
handle. The process-wide network and SDK database cache are never destroyed
when an individual session closes. Different TLS profiles require separate
processes; retiring a provider object does not reset the native network.

JSON commands admit get, set, clear, clear_range, range, atomic, read_version,
begin, commit and rollback. Keys, values and range endpoints use UTF-8 text by
default or explicit ``key_encoding``, ``value_encoding``, ``begin_encoding``
and ``end_encoding`` equal to ``base64``. No implicit string conversion occurs.
Atomic operations use native byte operands and the explicitly admitted native
operation name. FoundationDB remains responsible for operand semantics.

An explicit transaction retains native reads, writes and conflict ranges until
commit or rollback. Without begin, each command owns one native transaction.
Range pages preserve one read transaction and its native version; they do not
restart at newer versions or silently truncate at 10000 records. Pages contain
at most 256 entries with a 1 MiB target. Native transaction timeout still applies
to slow consumers. Keys and values are returned as hex with their encoding
identified. Committed/read versions are decimal text.

The driver never invokes on_error or repeats a transaction. Failed operations
quarantine the session conservatively; native error codes remain visible.
Unknown commit does not become rollback. Local cancellation stops delivery and
quarantines ownership until cleanup, without asserting server cancellation.
Closing cancels only the locally retained, undecided transaction and releases
its references. It does not undo committed effects. Metadata and administration
use independent temporary native database references and existing provider forms.

Portable qualification
----------------------

Run ``python tools/cdeadmin_foundationdb_driver_platform_gate.py --route
ROUTE.json --evidence OUTSIDE_REPOSITORY``. Supply ``cluster_file``, the native
``fdbcli_path`` and a writable disposable namespace. The gate owns a random key
prefix and removes it. It checks exact binary values, isolated sessions,
rollback, native commit, conflicts, 10017 entries, cancellation and an injected
client failure after a native commit acknowledgement. The last check is not a
wire-level dropped-packet test. Windows/macOS teams must run the same gate with
their native client library and CLI before accepting those platform packages.

TLS uses ``tls_mode: verify-peers``, ``tls_ca_file``, optional client certificate
and key paths, and native ``tls_verify_peers`` policy. Every coordinator in the
cluster file must agree with the route's TLS mode. Native peers are checked by
FoundationDB's explicit policy, rather than an invented HTTP hostname rule.
Security material changes require a new process; certificate contents and key
password changes are checked even when their file names remain unchanged.
