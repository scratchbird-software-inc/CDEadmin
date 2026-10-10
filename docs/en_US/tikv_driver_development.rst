TiKV native driver contract
===========================

TiKV 8.5.6 uses the pinned official client-go bridge. Query sessions retain an
owned helper process with one ordered JSON request/response stream. The helper
pins its route and TLS configuration for its lifetime. Process loss, timeout or
malformed output quarantines the owning session without replay. The bridge is
built for the receiving platform; it is not replaced by a MySQL compatibility
connection. Existing native PD, region, placement, TTL and operational forms
remain available through the engine's administration provider.

RawKV get, put, delete, CAS, TTL and scan remain RawKV operations. Raw scans are
bounded pages over a changing keyspace and do not claim a transaction snapshot.
An explicit total limit is honored; scan_all continues beyond 10000 records.
Native binary keys and values use the existing base64 fields without lossy text
coercion. Native uint64 identifiers and timestamps cross JSON as decimal text.

BEGIN creates a retained TxnKV transaction; txn_get, txn_set, txn_delete and
txn_scan operate only on it. COMMIT detaches the transaction before dispatch,
so a lost reply cannot trigger a second commit or guessed rollback. ROLLBACK
uses the native client. Raw operations are refused while a TxnKV transaction
is active. Snapshot scans retain the same transaction timestamp across pages.
Pessimistic writes acquire native locks before staging. API-v1-with-TTL refuses
TxnKV operations as required by native storage compatibility. No application
transaction retry is performed; native region routing and RPC behavior remain
client-go owned.

Local cancellation stops delivery. It does not claim that a dispatched mutation
was cancelled. Close releases the helper and its retained resources; helper loss
may leave server-side transaction resolution and lock cleanup pending. Windows
and macOS acceptance requires building the pinned Go helper and running the
portable driver gate against native TiKV/PD, including the deployment's TLS mode.

Build and qualify
-----------------

Build with ``python tools/cdeadmin_build_tikv_helper.py --output OUTSIDE_REPO
--evidence OUTSIDE_REPO.json`` using the pinned Go module. Set Go build/module
caches and temporary directories to the designated platform work area.
Run ``python tools/cdeadmin_tikv_driver_platform_gate.py --route ROUTE.json
--helper HELPER --evidence OUTSIDE_REPOSITORY``. The gate creates and removes
random owned keys, exercises RawKV and TxnKV separately, native pessimistic
locking, TLS when configured, cancellation and a post-acknowledgement commit
fault. It does not claim that fault is packet loss.

Verified deployments supply ``tls_ca``, client certificate/key when required,
and ``pd_http_scheme: https``. The driver refuses inconsistent native/PD TLS
policies. Transaction read key lists may use ``keys_base64`` for arbitrary
binary keys; they cannot also supply a nonempty UTF-8 ``keys`` list.
