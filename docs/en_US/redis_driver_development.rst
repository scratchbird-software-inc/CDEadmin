Redis native driver contract
============================

Redis 8.6.2 uses redis-py 6.4.0 and RESP3. Standalone and Sentinel query sessions
reserve one native connection, preserving SELECT, WATCH and MULTI/EXEC state.
Cluster sessions use native routing and same-slot transactional pipelines.
Redis owns EXEC results, WATCH aborts and per-command errors; an EXEC array
containing an error does not mean other commands were rolled back. Cluster
transaction queueing is client-side until the native pipeline dispatches EXEC.

Both socket retries and cluster error retries are disabled. Connection loss,
timeout, failed cleanup or an uncertain EXEC quarantines the owning session
without replay. Native MOVED/ASK handling remains redis-py owned. Closing a
session disconnects its reserved connection before pool release. It does not
claim to undo an executed mutation. Metadata uses independent connections.

Command text remains supported. JSON token arrays or ``operation: command``
with ``arguments`` admit binary envelopes ``{"$binary":"base64"}`` and exact
integer envelopes ``{"$integer":"9007199254740993"}``. Replies retain unsafe
integers, nonfinite doubles, binary strings, sets, map key identity and native
error items. Top-level sequences are delivered as indexed pages, at most 256
items with a 1 MiB target. Native aggregate replies still require redis-py's
RESP parsing allocation; use cursor operations for large collections.

``operation: scan`` iterates native SCAN cursors, including Cluster node cursors.
It has no 10000-key success cutoff and makes no snapshot or deduplication claim.
``operation: subscribe``, ``psubscribe`` and ``ssubscribe`` use a dedicated native
Pub/Sub resource, with explicit message limit and timeout. ``operation: monitor``
uses a dedicated native monitor connection. Raw mode-switching subscription and
monitor commands are refused so push messages cannot corrupt ordinary replies.
Local cancellation stops delivery without asserting mutation cancellation.

Redis-native data structures, scripts, functions, modules, ACL, Sentinel,
Cluster, persistence and operational administration retain their existing
engine-specific forms. Authentication and TLS key passwords use secret leases.
Verified TLS does not fall back to plaintext. Windows/macOS qualification uses
the portable native driver gate and each platform's TLS/client package.

Portable qualification
----------------------

Run ``python tools/cdeadmin_redis_driver_platform_gate.py --route ROUTE.json
--evidence OUTSIDE_REPOSITORY`` against a writable disposable deployment.
``--password-file`` supplies a local fixture password through a secret lease;
it is never included in the receipt. The gate removes its randomly named keys.
Run separately for standalone, verified TLS, Cluster and Sentinel routes.
The native gate checks bounded SCAN delivery, transactions, Pub/Sub, monitoring
and a client fault after an acknowledged EXEC. A separate qualification fixture
can test actual discarded RESP replies; those two fault mechanisms are distinct.

MONITOR on a Cluster session observes the selected default node, not the whole
cluster. Explicit node endpoints allow other nodes to be inspected. Pub/Sub
message limits include native subscription acknowledgements. SCAN may return
keys more than once while the keyspace changes, as specified by Redis.
