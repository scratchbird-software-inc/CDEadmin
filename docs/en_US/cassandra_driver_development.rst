Apache Cassandra native driver contract
======================================

Cassandra 5.0.8 uses cassandra-driver 3.30.1 and its native CQL protocol.
The complete Cassandra catalog, SAI, materialized views, UDTs, functions,
aggregates, roles, permissions and operational-tool forms remain Cassandra
owned. CQL wire mechanics may be reused across profiles; YugabyteDB transaction
syntax, catalogs and version admission are not imported into this profile.

One operation owns its session through terminal observation. Prepared binary
bindings preserve exact integers, decimals, blobs, UUIDs, timestamps and
collections. Native page fetches feed ordered pages of at most 256 rows with
a 1 MiB target and two queued pages; one large record may exceed the target.
Duplicate column labels retain ordinal identity. No 10000-row success cutoff
is imposed. Native tracing IDs and server warnings remain observations.

FallthroughRetryPolicy and explicitly non-idempotent statements prevent
application mutation retries and speculative execution. Native ambiguous
failures quarantine the session without replay. Local cancellation stops
result delivery; it does not assert server cancellation, transaction rollback
or the absence of a mutation. Close waits for the owner worker and preserves
failed session/cluster cleanup for retry.

Cassandra consistency levels, serial consistency, logged/unlogged batches and
LWT applied/not-applied results remain server owned. No general SQL-style
BEGIN/COMMIT/ROLLBACK interface is advertised. Metadata uses independent
connections. Credentials and verified TLS use the native driver; verification
failure never downgrades to plaintext. Platform teams run the portable native
gate against their exact package before Windows/macOS acceptance.

Run ``python tools/cdeadmin_cassandra_driver_platform_gate.py --route ROUTE.json
--evidence OUTSIDE_REPOSITORY`` with an owned writable Cassandra namespace.
Use native protocol version 5, ``auth_mode: password`` and ``username``. Verified
TLS uses ``tls_mode: system-ca``, ``tls_ca_file`` and hostname checking. The gate
creates and drops a uniquely named keyspace, including its types and tables.
``--reply-loss`` qualifies a native acknowledged mutation followed by an injected
client response failure; it does not claim a protocol-v4 proxy tested v5 framing.

Duration bindings use ``{"type":"duration","value":{"months":"1",
"days":"2","nanoseconds":"9007199254740993"}}``. Integer components stay text
until native conversion. UDTs can bind ordered field tuples; results retain UDT
field names. Vector values retain their native ordered float components.
