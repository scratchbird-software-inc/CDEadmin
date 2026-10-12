OpenSearch SQL/PPL driver contract
=================================

OpenSearch 3.6.0 with SQL/PPL plugin 3.6.0.0 uses a retained session worker.
SQL drains JDBC cursors without a local row cap, preserving ordinal row arrays
and native schema (including duplicate names). Each cursor response replaces
the prior token. Exhaustion releases ownership; cancellation/failure closes the
latest cursor through POST /_plugins/_sql/close. Failed close retains ownership
for cleanup retry. Cursor tokens are not exposed in results or diagnostics.

PPL does not support cursor pagination. Its fetch_size is a native result limit,
not a page size. The driver does not inject the legacy 1,000-row default for PPL.
Explicit fetch_size and server query size limits remain native constraints;
SQL and PPL results state that server limits apply. No SQL OFFSET rewriting, retries or
fallback to a different query engine is performed. Unsupported paging queries
return their native failure and quarantine the session.

Plain text uses route query_language. A JSON envelope accepts source, language
(sql or ppl), parameters and fetch_size. The normal request language override
is also honored. SQL defaults to a 256-row fetch; PPL uses only an explicitly
configured fetch limit. Native data sources and parameter bindings remain
available. Large integers use $integer envelopes. Pages contain at most 256
rows or approximately 1 MiB, except one large row. Individual native HTTP
responses retain the existing transport bound and fail visibly on overflow.

There are no multi-request transactions. Cancellation stops delivery and
releases query resources; it does not imply rollback. Existing language and
native administration forms remain available. TLS and credentials use the
verified bounded HTTP transport. The portable native gate covers SQL cursor
exhaustion, exact values and PPL native limits; platform teams must qualify
Windows/macOS independently.

The 3.6.0 native fixture returns 10,000 rows for a 10,017-row SQL cursor
query even with query.size_limit and the index result window set to 20,000.
The legacy cursor computes remaining rows from the search total hit count
(SelectResultSet.rowsLeft), which is bounded by native hit tracking. The
driver reports native totals and server_limit_applies; cursor exhaustion
is not a claim that every matching document was returned. Use the native
scan operation when an exhaustive document scan is required. The gate checks
this observed engine behavior; isolated tests also prove delivery beyond
10,000 rows when native responses supply them. No engine setting or query
is silently rewritten to bypass native behavior.

Portable qualification
----------------------

Run from a development checkout with its Python requirements installed::

    python tools/cdeadmin_opensearch_sql_ppl_driver_platform_gate.py --route ROUTE.json --password-file PASSWORD_FILE --evidence EXTERNAL_DIRECTORY

The route contains connection options without inline secrets. The password
file must be private to the developer account. Evidence must be outside the
source checkout. The gate creates and removes uniquely named native fixtures
and records platform details and source hashes. Use a dedicated test service;
a passing Linux receipt is not Windows or macOS qualification.
