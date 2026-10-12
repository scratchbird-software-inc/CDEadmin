Milvus driver contract
======================

The Milvus 2.6.5 factory uses PyMilvus 2.6.5 with a unique connection alias
and owned gRPC channel per session. One worker owns each active operation.
Metadata uses independent temporary clients. No multi-operation SQL
transaction or rollback is advertised. Consistency and visibility remain
native Milvus behavior; a successful write is not a flush or a load guarantee.

Query JSON accepts query, query_iterator, search, search_iterator,
hybrid_search, get, insert, upsert and delete. Query uses a native iterator
unless requesting count(*); search retains native top-K limits and query
vector indices. Explicit iterators stream to exhaustion without a local
10,000 record cap. Hybrid requests become native AnnSearchRequest objects;
ranker selects rrf (k) or weighted (weights). Request options stay native.

Values use $integer for large Int64, $binary for bytes, $float for nonfinite
values and $sparse for dimension/value pairs. These envelopes work in both
query JSON arguments and results. Separate parameter bindings are refused. Dense vectors and dynamic fields retain their
native structure. Pages contain up to 256 matches or about 1 MiB, except a
single native entity may exceed the byte target. Native gRPC messages have a
64 MiB transport limit; oversized results fail visibly rather than truncate.

gRPC retries are disabled. A per-channel interceptor prevents PyMilvus's
RPC-failure retry decorator from replaying requests, including when it would
otherwise prefer a timeout over retry_times=0. Transport and server failures
are redacted and quarantine the session; no uncertain mutation is replayed.
Cancellation stops local delivery and closes retained iterators once the
worker returns; it does not undo accepted writes. Failed cleanup retains
ownership for another close attempt.

TLS uses verified gRPC channel credentials, custom CA and optional client
certificate/key. server_name selects the authenticated peer name. Encryption
is never implemented by disabling certificate checks, including require and
verify-ca route modes. Credentials are leased through the existing service.
Existing collection/index/load/partition/security/resource-group forms remain
native and separately authorized. Windows/macOS teams run the portable native
gate themselves; Linux qualification does not qualify another platform.

Portable qualification
----------------------

Run from a development checkout with its Python requirements installed::

    python tools/cdeadmin_milvus_driver_platform_gate.py --route ROUTE.json --password-file PASSWORD_FILE --evidence EXTERNAL_DIRECTORY

The route contains connection options without inline secrets. The password
file must be private to the developer account. Evidence must be outside the
source checkout. The gate creates and removes uniquely named native fixtures
and records platform details and source hashes. Use a dedicated test service;
a passing Linux receipt is not Windows or macOS qualification.
