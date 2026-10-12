Neo4j driver contract
====================

The 2026.04.0 provider uses neo4j Python 6.3.0. Each query session owns its
driver, native session, explicit transaction and single worker. Only one
result may be active. Queries use native run, never managed transaction
callbacks. Commit/rollback use the original transaction. Errors quarantine
the owner; no application replay occurs. Existing authentication, Bolt TLS,
routing, impersonation and edition-specific forms retain their contracts.

Results stream to exhaustion without the old 10,000 record cap. Pages carry
native columns, graph records, ordinal values and a final summary containing
counters, plans and bookmarks. Nodes retain labels, element IDs and properties;
relationships retain types and endpoints; paths retain order. Temporal values
preserve nanoseconds; spatial values preserve coordinates/SRID; vectors retain
their native dtype and big-endian bytes. Pages have at most 256 rows or about
1 MiB, except that a single native value may exceed the byte target.

Parameters support $integer, $binary, $float, $neo4j_temporal, $neo4j_point and
$neo4j_vector envelopes. Temporal values have type and value fields; points
have srid and coordinates; vectors have dtype and base64 data. Ordinary maps
and lists remain native Cypher parameters. Graph entities are result values,
not parameter identities. Use native elementId predicates explicitly.

Local cancellation does not prove server rollback. Closing delegates to the
synchronous driver's close; this can finish an outstanding auto-commit query.
It does not resolve a previously unknown outcome. An unresolved worker retains its owner
until safe cleanup; close failure leaves that owner available to retry close.
Windows/macOS teams run the same native platform gate against their test
deployment. Linux evidence alone does not qualify another platform.
