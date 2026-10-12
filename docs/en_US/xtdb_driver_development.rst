XTDB native driver contract
===========================

XTDB 2.1.0 is admitted by xt.version(), using psycopg 3.3.4 as transport.
Retained execution does not impose PostgreSQL catalogs, savepoints, DISCARD ALL,
or transaction semantics on XTDB. Existing bitemporal document administration,
valid/system-time selection, row identity and authentication forms remain native.

Query execution returns an operation before waiting for the first result. One
operation owns the session until its terminal result is observed. Ordered result
sets retain column ordinals and stable keys. XTDB rejects duplicate SQL
projections; the driver preserves that native refusal. Browser pages target 256
rows/1 MiB with two queued pages; native driver buffering is separate. There is
no silent 10000-row truncation. Exact integers outside JavaScript's safe range
are represented with $xtdb_type=integer and a decimal-text value. Parameters
accept the same integer envelope, and binary uses $xtdb_type=varbinary with
base64. Ordinary JSON documents remain native JSONB parameters. No unknown
mutation or transaction decision is automatically replayed.

Bare BEGIN follows the configured native transaction mode, timezone and async
policy. Command tags are observed, never rewritten into a successful commit.
A response to an asynchronous commit does not prove that indexing has completed.
Native await/basis operations remain available through SQL. Catalog operations
use separate owned sessions and cannot roll back a user's pending transaction.

Cancellation shuts down the retained socket and quarantines the session. It does
not assert rollback, transaction failure or indexing completion. XTDB 2.1's
cancel dispatcher selects a gateway-local process ID; the driver does not use a
second, potentially differently routed cancellation connection. Pool admission
is credential/configuration-specific, and physical leases are discarded on
release until engine-specific reset isolation is qualified. Failed cleanup
retains ownership for retry. TLS verification never downgrades on failure.

Platform teams run the portable native driver gate against an owned XTDB node,
retaining exact source hashes and cleanup receipts. Native temporal tests use
uniquely named tables and ERASE only their owned documents. Windows/macOS runtime
acceptance remains separate from Linux driver qualification.
