InfluxDB driver contract
========================

The 3.9.0 Core/Enterprise HTTP provider streams SQL and InfluxQL JSONL without
the old 10,000 point cap. Each session owns one worker and one active request.
The route selects query_language; a JSON query envelope may explicitly select
sql or influxql using operation=query, language, source and parameters.
Plain editor source uses the route's language. Flux and SQL transactions are
not advertised for this engine version.

Pages contain up to 256 points or approximately 1 MiB; a single line may be
up to 16 MiB. Signed/unsigned integers beyond JavaScript's exact range use
the existing $integer string envelope. Timestamps remain native strings,
including fractional seconds; native JSONL does not carry Arrow schema types.
Null/missing fields retain their server JSON representation. Named parameters
are sent to the native endpoint, never interpolated into SQL.

A JSON write envelope uses operation=write, line_protocol and optional
precision (ns/us/ms/s), accept_partial and no_sync. Both booleans default to
false and must be booleans. The server owns validation, duplicate-point merge,
partial-write and durability behavior. HTTP rejection may still accompany
accepted points when partial writes were explicitly enabled; never replay
automatically. Read-only routes refuse this write path.

Cancellation closes local delivery when the worker returns; no server abort
or rollback is implied. Network/HTTP/stream errors quarantine the session.
Native requests never redirect or retry. Existing token, cache, database,
retention and processing-engine forms retain their engine-specific gates.
TLS and leased token credentials use the existing HTTP route.

The platform gate uses a random database and removes it after checking native
line-protocol writes, SQL/InfluxQL streaming and exact values. Windows/macOS
teams run the same gate; Linux proof does not qualify another platform.
