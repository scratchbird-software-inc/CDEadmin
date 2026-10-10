OpenSearch native driver contract
=================================

The OpenSearch 3.6.0 provider retains one HTTP worker per query session and
preserves native request semantics. There are no SQL transaction controls.
Plain editor JSON remains Query DSL with native size/from/search_after, PIT,
aggregations, scores, highlights and shard status. It does not silently turn
a top-K request into a full scan. No local 10,000-hit truncation is applied.

Explicit operation=scan accepts index, body, batch_size (1..256) and scroll
keep-alive, drains a native scroll and clears the latest scroll ID on normal
completion or cancellation. IDs are retained for cleanup retry if clear fails.
No OFFSET query rewriting occurs. Timed-out or failed-shard scan pages are
reported as partial and then fail; they are not a successful exhaustive scan.

Operation=bulk accepts actions (native NDJSON objects) and query options.
Every native item status/error is returned, including partial success. No
failed item is replayed automatically. Operation=request provides the native
REST method, relative path, query and body for engine-specific APIs, including
PIT lifecycle, multi-search, tasks and optimistic concurrency controls. Absolute
URLs, redirects and inline path query strings are rejected. Read-only routes
refuse bulk and generic mutating methods; server privileges remain authority.

Large JSON integers use $integer envelopes in parameters/results. Pages hold
at most 256 records or approximately 1 MiB, except a single native object can
exceed that target. Requests and individual HTTP responses retain the existing
2 MiB/8 MiB bounds and fail explicitly on overflow. Scrolls permit arbitrarily
many bounded responses. TLS, leased credentials, compression and timeouts use
the existing route. Uncertain outcomes quarantine the session. Cancellation
stops local delivery; it never implies rollback of a bulk or REST mutation.

Native administration forms retain their resource-specific capabilities.
The portable native gate qualifies a random index, scan, bulk partial success
and exact values. Windows/macOS teams must run it on their native platforms.

Portable qualification
----------------------

Run from a development checkout with its Python requirements installed::

    python tools/cdeadmin_opensearch_driver_platform_gate.py --route ROUTE.json --password-file PASSWORD_FILE --evidence EXTERNAL_DIRECTORY

The route contains connection options without inline secrets. The password
file must be private to the developer account. Evidence must be outside the
source checkout. The gate creates and removes uniquely named native fixtures
and records platform details and source hashes. Use a dedicated test service;
a passing Linux receipt is not Windows or macOS qualification.
