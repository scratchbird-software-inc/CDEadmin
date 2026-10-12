Apache Ignite native driver contract
===================================

The 2.17.0 profile uses pyignite 0.6.1 thin-client SQL and cache operations,
with separate native REST and control-script administration. Each user session
has a dedicated execution worker: pyignite transaction context must survive
between calls and must never be shared between user sessions. Native cache
transactions use configured concurrency, isolation, timeout and label. SQL is
not silently admitted into a cache transaction: this driver refuses SQL while
such a transaction is active because ordinary Ignite SQL tables do not inherit
cache transaction atomicity.

Only one operation owns a session through terminal result observation. SQL
bindings are passed as native query arguments. Result pages retain native
column identity and exact integer, decimal, binary, UUID and temporal values.
No application-level retry or replay is performed. Failed native calls or
transaction decisions quarantine the session; a disconnected transport or
local cancellation is not evidence of rollback. Cancellation stops local
result delivery, and session release waits for native work to finish before
closing the connection. A failed release keeps ownership for retry.

Metadata and administration use separate native attachments. They cannot
commit or roll back a user's pending cache transaction. Session close requests
native rollback of a known open transaction before releasing its attachment;
uncertain decisions are never repeated. TLS and credential settings remain
engine-specific, with unsupported verification policies rejected explicitly.
Native release gates and platform receipts qualify the exact driver/server
combination; Linux checks do not constitute Windows/macOS acceptance.

TLS ``verify-full`` verifies both chain and hostname before credentials are
sent. ``verify-ca`` verifies the chain; ``required`` requests encryption without
identity verification. Minimum TLS 1.2/1.3 and client certificates are explicit.
The provider composes native handshake codecs with a per-client SSL context;
it does not patch global pyignite modules. Transport failures are surfaced
without retransmitting the application request.

SQL parameters use a positional JSON array. Exact envelopes use ``type`` and
``value`` for integer, decimal, binary (base64), UUID and temporal values.
Binary-object envelopes retain native type name, field schema and exact field
values; map representations retain typed keys. Temporary metadata/admin
attachments are closed at the operation boundary, including error paths.

Run ``python tools/cdeadmin_ignite_driver_platform_gate.py --route ROUTE.json
--evidence OUTSIDE_REPOSITORY`` against an owned writable active cluster. The
gate prompts for the password, creates uniquely named tables and caches, and
removes them. The TLS receipt qualifies the thin-client connection; configure
REST HTTPS separately when that administrative route crosses a trust boundary.
