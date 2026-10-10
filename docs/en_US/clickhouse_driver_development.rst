ClickHouse driver contract
==========================

The default 25.12.10.7 provider retains a worker and a unique HTTP session ID
per query session. SQL, named typed parameters, session settings, temporary
tables and administration use native ClickHouse semantics. Explicit SQL
transactions are not advertised by this profile. Read-only routes use the
server's readonly setting; lexical SQL classification is not authorization.

Query responses stream JSONCompactEachRowWithNamesAndTypes, preserving
ordinal columns (including duplicate names) and native type names. UInt64,
Int64 and Decimal values are quoted by the server for lossless JSON delivery.
There is no implicit row cap. Pages have at most 256 rows or approximately
1 MiB; one row may exceed that target up to the 16 MiB line bound. A caller
must use the selected response format; incompatible explicit FORMAT clauses
fail visibly. Server errors after earlier pages are terminal errors, never
successful end-of-stream. SQL INSERT with native input FORMAT is supported.

HTTP requests have no redirect or automatic retry. Each query exposes its
query_id for native system.processes/query_log diagnosis. Local cancellation
stops delivery and closes the response when the worker returns; it does not
confirm KILL QUERY or rollback. Timeouts and ambiguous failures quarantine
the session. Existing administration forms retain their native contracts.
TLS, credentials, compression and timeouts use the existing HTTP route.

Windows and macOS use the same Python/urllib3 implementation and platform
gate as Linux; receiving teams must run that gate themselves. Native HTTP
session state expires according to ClickHouse session timeout after close.
