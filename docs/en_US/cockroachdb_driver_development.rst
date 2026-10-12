CockroachDB native driver contract
=================================

The admitted profile is CockroachDB 26.1.3 using psycopg's PostgreSQL wire
transport. CockroachDB owns transaction semantics, retry decisions and cluster
behavior. Protocol compatibility does not admit PostgreSQL-only features.

Retained sessions have one execution owner. Native text results preserve exact
values and ordinal column identities. Ordered result sets are presented through
a two-page queue with 256-row/1 MiB page targets; a single large value can exceed
the byte target. Native libpq result buffering is outside this bound. Named and
positional bindings accept explicit exact integer, decimal and binary envelopes.
Cancellation targets the original connection's native backend key. Connection
loss never causes automatic reconnection or mutation replay in a retained session.

The cancellation transport and original query have separate observations.
CockroachDB may close the encrypted cancel socket without TLS close_notify,
causing libpq to report SSL EOF even when cancellation reaches the server.
Record a sanitized transport error and an unconfirmed cancel receipt; continue
observing the original query. Only its native completion determines whether
the statement was cancelled, completed, or has an unknown outcome. Do not
retry cancellation through plaintext or infer transaction rollback.

SQLSTATE 40001 requests caller-controlled transaction retry; the driver never
replays the user's work. SQLSTATE 40003 is an ambiguous outcome and quarantines
the session. Connection failures and missing native outcome evidence also block
reuse. Commit/rollback observations include native command status and native
transaction status; a successful COMMIT command whose status is ROLLBACK is not
reported as committed. Retrying an entire transaction requires explicit caller
intent and application knowledge of external effects. Native retry savepoint
commands remain available as SQL without automatic helper replay.

Optional metadata statements on a retained session use a native savepoint.
Only admitted missing/unsupported/permission-denied catalog errors may be skipped
after successful savepoint rollback. Serialization errors, connection loss and
failed savepoint recovery propagate. An optional catalog read must never roll
back the user's entire transaction. Administration shares exclusive ownership
with query execution, cancellation and transaction control.

Pools are scoped by endpoint namespace, full connection configuration, credentials
and pool policy. Changed credentials or TLS options cannot reuse an old pool just
because the route ID is unchanged. Existing sessions retain their original
connection. Cleanup returns a connection at most once; failed native release
retains ownership for retry. Uncertain connections are closed before pool return.
Shutdown attempts every owned session and pool. Native TLS verification remains
controlled by the explicit endpoint route and is never weakened for fault tests.

Qualification must exercise real CockroachDB exact values, paging, cancellation,
retained decisions, native serialization retries, lost COMMIT confirmation,
metadata isolation, credential/TLS pool separation and release. Portable gates
use an owned database and explicit server route. Windows/macOS receiving teams
must run those gates with their packaged interpreter and native libraries;
Linux results do not imply receiving-platform or UX acceptance.

Pool release first rolls back pending work, then runs native DISCARD ALL outside
a transaction to clear role, settings, prepared statements, sequence state and
temporary objects. Driver transaction defaults are cleared before the next
route initializes them. Implicit psycopg preparation is disabled so its local
cache cannot survive DISCARD ALL. A failed reset closes the native connection.

Platform execution
------------------

Install the project's Python dependencies, including psycopg and psycopg_pool,
using the packaged interpreter. Supply an explicit server route JSON with host,
port, user and TLS options; omit database and password. The gate creates and
drops its own random database and prompts for the password. Certificate
authentication uses ``--no-password`` and explicit sslcert/sslkey/sslrootcert.
The account needs database creation and the native retry test builtin. The gate
enables allow_unsafe_internals only inside its owned test session.

Run ``python tools/cdeadmin_cockroachdb_driver_platform_gate.py --route ROUTE
--evidence OUTSIDE_REPOSITORY``. The output directory must be new. Use a real
26.1.3 server for the admitted profile. With verify-full, the gate checks an
incorrect hostname and invalid principal; certificate routes also test an
incorrect trust anchor. The optional ``--reply-loss`` test requires a separate
explicit plaintext loopback fixture and never weakens the production TLS route.
It drops a decoded native COMMIT confirmation and verifies the committed row
independently while the original session remains blocked from replay. Preserve
the source hashes and summary with each native Windows/macOS run.
